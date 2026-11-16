#!/bin/bash
set -euo pipefail
for actor in ${V_CAPTURE_ACTORS:-ichika miku}; do
 for variant in off no-hair no-face no-classes no-skin no-outline no-eyes no-mapping all; do
  if [[ -f /work/gakumas/work/codex/HANDOFF_NOW ]]; then echo HANDOFF_NOW; exit 75; fi
  if grep -aq LIVE_QUIT "/work/motion-bake/task-W/captures/$actor/$variant/player.log" 2>/dev/null; then
   if python3 - "$actor" "$variant" <<'PY_CACHE'
import hashlib,json,pathlib,sys
root=pathlib.Path('/work/motion-bake/task-W');actor,variant=sys.argv[1:];manifest=root/'content'/(actor+'-'+variant)/'manifest.json'
if not manifest.exists():sys.exit(1)
entries={e['name']:e for e in json.loads(manifest.read_text())['bundles']}
paths=list((root/'output'/actor/variant).glob('mdl*.unity3d'))
if len(paths)!=3:sys.exit(1)
for p in paths:
 entry=entries[p.stem];staged=manifest.parent/entry['file'];expected=entry.get('sha256');digest=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
 if not staged.exists() or digest(p)!=expected or digest(staged)!=expected:sys.exit(1)
PY_CACHE
   then continue; fi
  fi
  bash /work/motion-bake/task-U/material-capture.sh "$actor" "$variant"
 done
done
