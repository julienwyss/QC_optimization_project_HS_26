import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
from qiskit import transpile
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2
from qiskit_algorithms import QAOA
from qiskit_algorithms.optimizers import COBYLA
from qiskit_optimization.applications import StableSet
from qiskit_optimization.converters import QuadraticProgramToQubo

class TranspiledSamplerV2:
    def __init__(self, backend, opt_level):
        self._backend = backend
        self._sampler = SamplerV2.from_backend(backend)
        self._opt_level = opt_level
        self._cache = {}
        self._basis_gates = ['id', 'rz', 'sx', 'x', 'cx', 'cz', 'u']

    @property
    def options(self):
        return self._sampler.options

    def _fingerprint(self, circuit):
        return (
            circuit.num_qubits,
            tuple((inst.operation.name, tuple(inst.qubits)) for inst in circuit.data)
        )

    def run(self, pubs):
        transpiled_pubs = []
        for pub in pubs:
            circuit = pub[0]
            rest = pub[1:]
            key = self._fingerprint(circuit)
            if key not in self._cache:
                self._cache[key] = transpile(
                    circuit,
                    basis_gates=self._basis_gates,
                    optimization_level=self._opt_level
                )
            transpiled_pubs.append((self._cache[key], *rest))
        return self._sampler.run(transpiled_pubs)

def repair_solution(G, nodes):
    """Greedy repair to enforce independence."""
    current = set(nodes)
    while True:
        conflicts = []
        for u in current:
            for v in G.neighbors(u):
                if v in current and u < v:
                    conflicts.append((u, v))
        if not conflicts:
            return list(current)

        counts = {}
        for u, v in conflicts:
            counts[u] = counts.get(u, 0) + 1
            counts[v] = counts.get(v, 0) + 1
        worst = max(counts, key=counts.get)
        current.remove(worst)

def _solve_attempt(attempt_id, G, operator, config):
    try:
        backend = AerSimulator(
            method="matrix_product_state",
            matrix_product_state_max_bond_dimension=config['BOND_DIM']
        )

        sampler = TranspiledSamplerV2(backend, config['OPT_LEVEL'])
        sampler.options.default_shots = config['SHOTS']

        optimizer = COBYLA(maxiter=config['MAX_ITER'])
        reps = config['REPS']

        if attempt_id % 2 == 0:
            betas = np.linspace(0.2, 0.8, reps)
            gammas = np.linspace(0.8, 0.2, reps)
            initial_point = np.concatenate([betas, gammas])
        else:
            initial_point = np.random.uniform(-np.pi, np.pi, 2 * reps)

        qaoa = QAOA(
            sampler=sampler,
            optimizer=optimizer,
            reps=reps,
            initial_point=initial_point
        )

        result = qaoa.compute_minimum_eigenvalue(operator)

        counts = result.eigenstate
        num_nodes = G.number_of_nodes()

        def weight(bs):
            return bs.count("1")

        candidates = []
        for key, prob in counts.items():
            if isinstance(key, int):
                bs = format(key, f'0{num_nodes}b')
            elif isinstance(key, str) and key.startswith('0x'):
                bs = format(int(key, 16), f'0{num_nodes}b')
            else:
                bs = key
            candidates.append((weight(bs), prob, bs))

        candidates.sort(key=lambda x: (-x[0], -x[1]))

        best_nodes = []
        for _, _, bs in candidates[:50]:
            raw = [i for i, b in enumerate(reversed(bs)) if b == '1']
            valid = repair_solution(G, raw)
            if len(valid) > len(best_nodes):
                best_nodes = valid

        return {"success": True, "size": len(best_nodes), "nodes": best_nodes}

    except Exception as e:
        return {"success": False, "error": str(e)}

def solve_graph_parallel(G, config):
    misp = StableSet(G)
    qp = misp.to_quadratic_program()
    qubo = QuadraticProgramToQubo(penalty=config['PENALTY']).convert(qp)
    operator, _ = qubo.to_ising()

    best_size = 0
    best_nodes = []

    n = G.number_of_nodes()
    m = G.number_of_edges()
    density = m / (n * (n - 1) / 2) if n > 1 else 0
    max_workers = config['MAX_WORKERS']
    #if density > 0.3:
    #    max_workers = min(2, max_workers)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_solve_attempt, i, G, operator, config)
            for i in range(config['MAX_ATTEMPTS'])
        ]

        for future in as_completed(futures):
            res = future.result()
            if res['success'] and res['size'] > best_size:
                best_size = res['size']
                best_nodes = res['nodes']

    return best_size, best_nodes
