#!/usr/bin/env bash
# Umumiy 3D katalogni serverga yuklash — bitta buyruq:
#
#   bash tools/katalog3d/yukla.sh                  # hammasi (~15 GB, ~1 soat)
#   bash tools/katalog3d/yukla.sh --max 30         # sinov uchun 30 ta
#
# Modellar data/katalog3d_modellar/ ga tushadi (yoki KATALOG3D_DIR). Uzilsa qayta ishga tushiring —
# tayyorlari o'tkazib yuboriladi. Kerak: python3, node 18+ (npm), internet (huggingface.co, 3d-api.si.edu).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${KATALOG3D_DIR:-$ROOT/data/katalog3d_modellar}"
if [ ! -d "$HERE/node_modules/@gltf-transform/core" ]; then
  (cd "$HERE" && npm install --no-audit --no-fund --omit=dev)
fi
mkdir -p "$OUT"
python3 "$HERE/yukla.py" "$ROOT/data/katalog3d/tanlov.jsonl" "$OUT" --node-path "$HERE/node_modules" "$@"
python3 "$HERE/tekshir.py" "$ROOT/data/katalog3d/katalog.json" "$OUT"
