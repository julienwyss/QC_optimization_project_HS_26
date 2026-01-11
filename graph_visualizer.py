import sys
import networkx as nx
import matplotlib.pyplot as plt


def visualize_graph(G, provided_solution, our_solution, title="Graph Visualization"):
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G, seed=42)
    node_colors = []
    graph_nodes = list(G.nodes())
    if not graph_nodes:
        return
    node_type = type(graph_nodes[0])
    provided_solution = set(node_type(n) for n in provided_solution)
    our_solution = set(node_type(n) for n in our_solution)
    for node in G.nodes():
        is_ours = our_solution and node in our_solution
        is_provided = provided_solution and node in provided_solution
        if is_ours and is_provided:
            node_colors.append('purple')
        elif is_provided:
            node_colors.append('green')
        elif is_ours:
            node_colors.append('red')
        else:
            node_colors.append('lightgray')
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=150)
    nx.draw_networkx_edges(G, pos, alpha=0.15)
    if G.number_of_nodes() <= 64:
        nx.draw_networkx_labels(G, pos, font_size=8, font_weight='bold')
    plt.plot([],[], marker="o", ms=10, ls="", mec=None, color="green", label="Provided Solution")
    plt.plot([],[], marker="o", ms=10, ls="", mec=None, color="purple", label="Both Solutions")
    plt.plot([],[], marker="o", ms=10, ls="", mec=None, color="red", label="Our Solution")
    total_nodes = G.number_of_nodes()
    provided_count = len(provided_solution)
    our_count = len(our_solution)
    edges_count = G.number_of_edges()
    stats_text = f"Nodes: {total_nodes}\nEdges: {edges_count}\nProvided: {provided_count}\nOur: {our_count}"
    ax = plt.gca()
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    plt.title(title)
    plt.legend()
    plt.axis('off')
    plt.show()




def read_solution_file(solution_path):
    import re
    nodes = set()
    int_line_re = re.compile(r'^\s*(\d+)\s*$')
    var_val_re = re.compile(r'.*#?(\d+)\s+([01])\s*$')
    with open(solution_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = var_val_re.match(line)
            if m:
                idx = int(m.group(1))
                val = int(m.group(2))
                if val == 1:
                    nodes.add(idx)
                continue
            m2 = int_line_re.match(line)
            if m2:
                nodes.add(int(m2.group(1)))
                continue
            parts = re.findall(r"\d+", line)
            if len(parts) == 1:
                nodes.add(int(parts[0]))
    return nodes

def read_graph_file(graph_path):
    edges = []
    with open(graph_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('c') or line.startswith('p'):
                continue
            if line.startswith('e'):
                parts = line.split()
                if len(parts) == 3:
                    try:
                        u = int(parts[1])
                        v = int(parts[2])
                        edges.append((u, v))
                    except ValueError:
                        continue
    G = nx.Graph()
    G.add_edges_from(edges)
    return G

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python graph_visualizer.py <graph_file> <provided_solution_file> <our_solution_file>")
        sys.exit(1)
    graph_file = sys.argv[1]
    provided_solution_file = sys.argv[2]
    our_solution_file = sys.argv[3]
    G = read_graph_file(graph_file)
    provided_solution = read_solution_file(provided_solution_file)
    our_solution = read_solution_file(our_solution_file)
    visualize_graph(G, provided_solution, our_solution)