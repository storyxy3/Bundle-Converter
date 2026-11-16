#!/bin/bash
# Independent content/capture directories; four native players, no editor/runtime changes.
set -euo pipefail
for actor in ichika miku; do
 for variant in off all rgb-only a-only neutral-a source mask-source-off mask-source-all sat-source-off sat-source-all ramp2 ramp3; do
  printf '%s %s\n' "$actor" "$variant"
 done
done | xargs -P4 -n2 bash -c '
 if [[ -e /work/gakumas/work/codex/HANDOFF_NOW ]]; then exit 75; fi
 PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/skin-study.py --actor "$1" --variant "$2" > "/work/motion-bake/task-W/batch-$1-$2.log" 2>&1
' _
