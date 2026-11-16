#!/bin/bash
set -euo pipefail
if [[ -e /work/gakumas/work/codex/HANDOFF_NOW ]]; then exit 75; fi
cp /work/motion-bake/task-U/skin-source-capture.mjs /work/motion-bake/task-W/source-capture.mjs
cp /work/motion-bake/task-U/skin-vite.config.ts /work/motion-bake/task-W/vite.config.ts
exec unshare --net bash -c '
 ip link set lo up
 cd /work/motion-bake/prsk3d
 export TMPDIR=/work/motion-bake/task-W/tmp
 export HARUKI_PERF_LOG=/work/motion-bake/task-W/perf.ndjson HARUKI_CONSOLE_LOG=/work/motion-bake/task-W/page-console.ndjson
 export PJSK_VIRTUAL_LIVE_CONTENT_ROOT=/work/motion-bake/content HARUKI_UNITY_BUILD_ROOT=/work/motion-bake/prsk3d/unity/Haruki3DMV/Build
 export RUNTIME_CHECK_QUERY="shows=shows-scene.json" RUNTIME_CHECK_PORT=4186
 mkdir -p "$TMPDIR"
 /work/.toolchains/bun/bun run node_modules/vite/bin/vite.js --configLoader runner --config /work/motion-bake/task-W/vite.config.ts --host 127.0.0.1 --port 4186 --strictPort > /work/motion-bake/task-W/serve.log 2>&1 &
 task_w_server=$!
 trap "kill $task_w_server 2>/dev/null || true" EXIT
 sleep 2
 for actor in ichika miku; do
  if [[ -e /work/gakumas/work/codex/HANDOFF_NOW ]]; then exit 75; fi
  W_ACTOR=$actor /work/.toolchains/node/bin/node /work/motion-bake/task-W/source-capture.mjs scene-ext-motion 28
 done
'
