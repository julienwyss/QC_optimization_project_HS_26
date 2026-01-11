import os
import time
import pandas as pd
import networkx as nx
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

from ibm_solver import solve_graph_parallel
from ibm_solver_large import solve_large_graph

INSTANCE_DIR = "instances"
SOLUTION_DIR = "solutions"
OUTPUT_FILE = "benchmark_stats_all.csv"

GENERATED_SOL_DIR = "solutionstemp"

SOLVER_CONFIG = {
    'MAX_WORKERS': max(1, multiprocessing.cpu_count() - 1),
    'REPS': 2,
    'MAX_ATTEMPTS': 12,
    'PENALTY': 1.5,
    'MAX_ITER': 50,
    'SHOTS': 1024,
    'OPT_LEVEL': 1,
    'BOND_DIM': 16
}

TIMEOUT_SECONDS = 7200
USE_FALLBACK_SOLVER = True
FALLBACK_TIMEOUT_SECONDS = 10800

def load_dimacs_graph(file_path):
    G = nx.Graph()
    with open(file_path, 'r') as f:
        for line in f:
            if not line or line.startswith('c'): continue
            parts = line.split()
            if parts[0] == 'p': G.add_nodes_from(range(int(parts[2])))
            elif parts[0] == 'e': G.add_edge(int(parts[1])-1, int(parts[2])-1)
    return G

def run_with_timeout_fn(fn, args, timeout_seconds):
    """
    Runs any function in a separate process with timeout.
    Returns (status, result)
    """
    with ProcessPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args)
        try:
            result = future.result(timeout=timeout_seconds)
            return "ok", result
        except Exception:
            future.cancel()
            return "timeout", None
        
def get_optimal_size(graph_name, sol_dir):
    """
    Supports both solution formats:
    1) Assignment format: x#i 0/1
    2) Index-list format: one node index per line
    """
    candidates = [
        f"{graph_name}.opt.sol",
        f"{graph_name}.bst.sol",
        f"{graph_name}.sol"
    ]

    for fname in candidates:
        path = os.path.join(sol_dir, fname)
        if not os.path.exists(path):
            continue

        selected_nodes = set()
        assignment_mode = False

        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("c"):
                    continue

                parts = line.split()

                # ---- Format A: x#i 0/1 ----
                if len(parts) >= 2 and parts[0].startswith("x#"):
                    assignment_mode = True
                    try:
                        if parts[1] == "1":
                            idx = int(parts[0][2:])  # x#21 -> 21
                            selected_nodes.add(idx)
                    except ValueError:
                        continue

                # ---- Format B: plain integer per line ----
                elif len(parts) == 1 and parts[0].isdigit():
                    selected_nodes.add(int(parts[0]))

        if selected_nodes:
            print(f"   [OPTIMAL SIZE] Loaded optimal/best solution from {path} with size {len(selected_nodes)}")
            return len(selected_nodes)

    print(f"   [OPTIMAL SIZE] No optimal/best solution file found for {graph_name}. Assuming optimal size 0.")
    return 0


def save_solution_file(graph_name, num_nodes, solution_nodes, size):
    """
    Saves the solution in the exact requested format:
    # Solution for model <name>
    # Objective value = <size>
    x#1 0
    x#2 1
    ...
    """
    os.makedirs(GENERATED_SOL_DIR, exist_ok=True)
    sol_path = os.path.join(GENERATED_SOL_DIR, f"{graph_name}.sol")
    
    sol_set = set(solution_nodes)

    with open(sol_path, 'w') as f:
        f.write(f"# Solution for model {graph_name}\n")
        f.write(f"# Objective value = {size}\n")
        
        for i in range(1, num_nodes + 1):
            val = 1 if (i - 1) in sol_set else 0
            f.write(f"x#{i} {val}\n")

def run_benchmark():
    multiprocessing.freeze_support()
    
    if os.path.exists(OUTPUT_FILE):
        try:
            existing = pd.read_csv(OUTPUT_FILE)
            processed = set(existing['Graph'].astype(str))
        except: processed = set()
    else:
        processed = set()

    files = sorted([f for f in os.listdir(INSTANCE_DIR) if f.endswith(".gph")])
    
    for f in files:
        name = os.path.splitext(f)[0]
        old_ratio = 0.0
        print(f"Processing: {name}, with starttime {time.strftime('%H:%M')}")
        # skip all the graphs that are already processed and have a ration of 1.0
        if name in processed:
            existing = pd.read_csv(OUTPUT_FILE)
            row = existing[existing['Graph'] == name]
            if not row.empty and row.iloc[0]['Ratio'] >= 0.90:
                print(f"Skipping {name} as it is already processed with optimal ratio.")
                continue
            else:
                print(f"Resuming {name} for potential better solution.")
                old_ratio = row.iloc[0]['Ratio']

        
        G = load_dimacs_graph(os.path.join(INSTANCE_DIR, f))
        if G.number_of_nodes() >= 1000:
            print(f"   [WARNING] Graph has {G.number_of_nodes()} nodes, this will be skipped to avoid excessive runtimes.")
            continue
        opt_size = get_optimal_size(name, SOLUTION_DIR)

        """ start = time.time()
        qaoa_size, qaoa_nodes = solve_graph_parallel(G, SOLVER_CONFIG)
        runtime = time.time() - start """
        start = time.time()
        too_many_edges = False
        status = ""
        fallback_timeout = False
        fallback_used = False

        # check if amount of edges is over 5000 and over 120 nodes if so imediately use fallback (otherwise it can be that the timeout still fails because of AER using C++ backend then python can't kill it)
        if (G.number_of_edges() > 5000 and G.number_of_nodes() >= 120):
            print("   [LARGE GRAPH] Starting divide-and-conquer solver...")
            too_many_edges = True

        if not too_many_edges:
            status, result = run_with_timeout_fn(
                solve_graph_parallel,
                (G, SOLVER_CONFIG),
                TIMEOUT_SECONDS
            )
            runtime = time.time() - start

            fallback_used = False
            fallback_timeout = False

            if status == "ok":
                qaoa_size, qaoa_nodes = result

        if status == "timeout" or too_many_edges:
            if status == "timeout":
                print(f"   [TIMEOUT] {name} exceeded {TIMEOUT_SECONDS//60} minutes")
                print("   [FALLBACK] Starting divide-and-conquer solver...")
                start = time.time()
            fb_status, fb_result = run_with_timeout_fn(
                solve_large_graph,
                (G, SOLVER_CONFIG),
                FALLBACK_TIMEOUT_SECONDS
            )

            fallback_used = True

            if fb_status == "ok":
                qaoa_size, qaoa_nodes = fb_result
            else:
                print(f"   [FALLBACK TIMEOUT] No solution found. Larger solver exceeder {FALLBACK_TIMEOUT_SECONDS//60} minutes.")
                qaoa_size, qaoa_nodes = 0, []
                fallback_timeout = True
            runtime = time.time() - start

        # only save solution if we found something that is better than the existing one (if there is an existing one)
        new_ratio = (qaoa_size/opt_size) if opt_size > 0 else 0
        if qaoa_size > 0 and new_ratio > old_ratio:
            save_solution_file(name, G.number_of_nodes(), qaoa_nodes, qaoa_size)

            stats = {
                "Graph": name,
                "Nodes": G.number_of_nodes(),
                "Edges": G.number_of_edges(),
                "Opt_Size": opt_size,
                "QAOA_Size": qaoa_size,
                "Ratio": (qaoa_size/opt_size) if opt_size > 0 else 0,
                "Time": runtime,
                "Timeout": int(status == "timeout"),
                "Fallback": int(fallback_used),
                "Fallback_Timeout": int(fallback_timeout)
            }
            
            # If the graph already has an entry in the CSV, update that row;
            # otherwise append a new row. This prevents duplicate entries when
            # rerunning a graph.
            # if we found new solution print it otherwise just say we saved it
            if os.path.exists(OUTPUT_FILE):
                out_df = pd.read_csv(OUTPUT_FILE)
                mask = out_df['Graph'].astype(str) == name
                if mask.any():
                    out_df.loc[mask, list(stats.keys())] = list(stats.values())
                    print(f" -> New improved solution found and saved: New QAOA Size: {qaoa_size}, Old QAOA Size: {int(old_ratio * opt_size)}, optimal/best size: {opt_size}")
                else:
                    out_df = pd.concat([out_df, pd.DataFrame([stats])], ignore_index=True)
                    print(f"Saving:  -> QAOA: {qaoa_size} | Opt: {opt_size} | Ratio: {stats['Ratio']:.2f}")
            else:
                out_df = pd.DataFrame([stats])
            out_df.to_csv(OUTPUT_FILE, index=False)
            processed.add(name)
        else:
            print(f" -> No improved solution found. Skipping save: New QAOA Size: {qaoa_size}, Old QAOA Size: {int(old_ratio * opt_size)}, optimal/best size: {opt_size}")
            processed.add(name)

if __name__ == "__main__":
    run_benchmark()