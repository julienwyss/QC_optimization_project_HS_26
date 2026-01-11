import networkx as nx
from ibm_solver import solve_graph_parallel, repair_solution

def solve_large_graph(G, config, max_subgraph_size=100):
    """
    Solves massive graphs by breaking them into smaller communities,
    relabeling them for the quantum solver, and stitching results back.
    """
    total_nodes = G.number_of_nodes()
    
    desired_max = config.get('MAX_SUBGRAPH_SIZE', max_subgraph_size)

    if total_nodes <= desired_max:
        return solve_graph_parallel(G, config)

    print(f"   [Large Graph Strategy] Splitting {total_nodes}-node graph into chunks of <= {desired_max} nodes...")

    subgraphs = split_until_small(G, desired_max)
    print(f"   [Large Graph Strategy] Split into {len(subgraphs)} subgraphs.")
    print(f"      Subgraph sizes: {[sg.number_of_nodes() for sg in subgraphs]}")

    sub_solutions = []
    
    for i, subgraph in enumerate(subgraphs):
        subgraph_relabelled = nx.convert_node_labels_to_integers(
            subgraph, first_label=0, ordering='sorted', label_attribute='original_label'
        )
        
        sub_config = config.copy()
        sub_config['MAX_ATTEMPTS'] = max(1, config['MAX_ATTEMPTS']) 

        print(f"      [Chunk {i+1}/{len(subgraphs)}] Solving subgraph with {subgraph_relabelled.number_of_nodes()} nodes and {subgraph_relabelled.number_of_edges()} edges...")
        
        _, sub_nodes_indices = solve_graph_parallel(subgraph_relabelled, sub_config)

        print(f"      [Chunk {i+1}/{len(subgraphs)}] Solved {subgraph_relabelled.number_of_nodes()} nodes and with {subgraph_relabelled.number_of_edges()} edges, got {len(sub_nodes_indices)} solution nodes.")

        for idx in sub_nodes_indices:
            original_node = subgraph_relabelled.nodes[idx]['original_label']
            sub_solutions.append(original_node)


    final_valid_nodes = repair_solution(G, sub_solutions)
    final_size = len(final_valid_nodes)
    
    print(f"   [Large Graph Strategy] Recombined. Raw: {len(sub_solutions)} -> Valid: {final_size}")
    
    return final_size, final_valid_nodes


def split_until_small_old(G, max_size):
    """
    Recursively splits graph until all subgraphs have ≤ max_size nodes.
    """
    if G.number_of_nodes() <= max_size:
        return [G]

    try:
        communities = nx.community.louvain_communities(G, seed=42)
    except:
        communities = nx.community.greedy_modularity_communities(G)

    result = []
    for comm in communities:
        sub = G.subgraph(comm)
        if sub.number_of_nodes() <= max_size:
            result.append(sub)
        else:
            result.extend(split_until_small(sub, max_size))

    return result

def split_until_small(G, max_size):
    """
    Guaranteed-terminating graph splitter.
    Uses community detection once; falls back to deterministic bisection.
    """
    n = G.number_of_nodes()
    if n <= max_size:
        return [G]

    # --- Try Louvain split ---
    try:
        communities = list(nx.community.louvain_communities(G, seed=42))
    except Exception:
        communities = list(nx.community.greedy_modularity_communities(G))

    # If Louvain fails to split, force bisection
    if len(communities) == 1:
        nodes = list(G.nodes())
        mid = n // 2
        return (
            split_until_small(G.subgraph(nodes[:mid]).copy(), max_size) +
            split_until_small(G.subgraph(nodes[mid:]).copy(), max_size)
        )

    result = []
    for comm in communities:
        sub = G.subgraph(comm).copy()

        # Safety: ensure strict size reduction
        if sub.number_of_nodes() >= n:
            nodes = list(sub.nodes())
            mid = len(nodes) // 2
            result.extend([
                G.subgraph(nodes[:mid]).copy(),
                G.subgraph(nodes[mid:]).copy()
            ])
        elif sub.number_of_nodes() <= max_size:
            result.append(sub)
        else:
            result.extend(split_until_small(sub, max_size))

    return result
