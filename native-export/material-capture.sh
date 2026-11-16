#!/bin/bash
set -euo pipefail
actor=${1:?}; variant=${2:?}
root=/work/motion-bake/task-W
content="$root/content/$actor-$variant"
args=()
for p in "$root/output/$actor/$variant"/mdl*.unity3d; do args+=(--bundle "$p"); done
/work/gakumas/tools/venv/bin/python /work/motion-bake/task-S/converter/stage-native.py /work/motion-bake/task-U/content-native "$content" "${args[@]}"
out="$root/captures/$actor/$variant"; mkdir -p "$out"
ulimit -n 65536
unshare -n env SDL_AUDIODRIVER=dummy PULSE_SERVER=unix:/nonexistent LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=${LP_NUM_THREADS:-16} xvfb-run -a -s '-screen 0 960x540x24' /work/gakumas/live-urp-native/Build/Linux/TrueEnd.x86_64 -force-vulkan -force-device-index 0 -noaudio -screen-width 960 -screen-height 540 -screen-fullscreen 0 --sample ttmr001 --data "$content" --mute --capture-fps 60 --start-time 27.8 --stop-time 28.1 --quit-after 1200 --screenshots 28 --capture-dir "$out" -logFile "$out/player.log" > "$out/console.log" 2>&1
