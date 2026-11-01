#!/usr/bin/env bash
# Render jobs sequentially. Each line: <shot> <variant> <scale> <samples>
# Frames already on disk are skipped, so the queue can be re-run after an interruption.
cd "$(dirname "$0")/.."
PY=${PY:-/opt/me-venv/bin/python}
while read -r shot variant scale samples; do
  [[ -z "$shot" || "$shot" == \#* ]] && continue
  echo "=== $(date +%T) $shot $variant scale=$scale spp=$samples"
  "$PY" -u blender/render.py --shot "$shot" --variant "$variant" --scale "$scale" --samples "$samples" 2>&1 \
    | grep -E "^\[(build|frame|done)\]|Error|Traceback"
done
