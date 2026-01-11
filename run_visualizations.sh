#!/usr/bin/env bash
set -euo pipefail

# Iteriere über alle Graph-Dateien in instances2 und erstelle Visualisierungen
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
INST_DIR="$BASE_DIR/instances2"
PROVIDED_DIR="$BASE_DIR/solutions"
OUR_DIR="$BASE_DIR/solutionstemp"
OUT_DIR="$BASE_DIR/visualizations"
PY_SCRIPT="$BASE_DIR/graph_visualizer.py"

mkdir -p "$OUT_DIR"

shopt -s nullglob
for graph in "$INST_DIR"/*.gph; do
  name=$(basename "$graph" .gph)

  # Suche nach provided solution: .opt.sol oder .bst.sol
  prov_opt="$PROVIDED_DIR/${name}.opt.sol"
  prov_bst="$PROVIDED_DIR/${name}.bst.sol"
  provided=""
  if [ -f "$prov_opt" ]; then
    provided="$prov_opt"
  elif [ -f "$prov_bst" ]; then
    provided="$prov_bst"
  else
    echo "[WARN] No provided solution for ${name}, skipping."
    continue
  fi

  our="$OUR_DIR/${name}.sol"
  if [ ! -f "$our" ]; then
    echo "[WARN] No our-solution for ${name} at ${our}, skipping."
    continue
  fi

  out_png="$OUT_DIR/${name}.png"
  echo "Processing ${name} -> ${out_png}"
  if ! py "$PY_SCRIPT" "$graph" "$provided" "$our" "$out_png"; then
    echo "[ERROR] Failed for $name"
  fi
done

echo "Done. Visualizations are in ${OUT_DIR}"
