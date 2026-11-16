#!/bin/bash
set -euo pipefail
for actor in ichika miku; do
 for variant in off no-hair no-face no-classes no-skin no-outline no-eyes no-mapping all; do
  if [[ -f /work/gakumas/work/codex/HANDOFF_NOW ]]; then echo HANDOFF_NOW; exit 75; fi
  PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/material-native.py --actor "$actor" --variant "$variant"
 done
done
