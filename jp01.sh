#!/bin/bash
# Haruki converter on JP01 (tooling). Run from anywhere on the local machine:
#   jp01.sh export                        skeletons (source + target) and the source motion's Humanoid curves
#   jp01.sh stage                         the source stage scene as haruki-external-stage/1
#   jp01.sh bake [frames] [render secs]   Humanoid curves -> target bone curves (unity/HumanoidBake), report, stick renders
#   jp01.sh ground [motion]               the baked motion on the original PJSK model on a flat ground + seek pre-roll check
#                                         (PlayMode test ExternalMotionGround of unity/Haruki3DMV)
# Env: CV_MOTION (curves name, default hski_all001), CV_MOTION_BUNDLE, CV_SCENE, CV_STAGE_BUNDLES, CV_STAGE_OUT,
#      HB_RANGE=start,end, HB_TRAVEL=keep|inplace, HB_TRAVEL_SCALE, EM_RENDER, EM_PROBES, EM_PREROLL, EM_FPS.
# Work root on JP01: /work/motion-bake (converter/ code copy, data/, out/, stage/, unity/ HumanoidBake project,
# haruki3dmv/ player project copy).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
host=jp01-host
work=/work/motion-bake
unity=/work/.toolchains/unity-6000.0.84f1/Editor/Unity
py=/work/gakumas/tools/venv/bin/python
gk=/work/gakumas
raw=/data/HarukiService/asset/data/assets/raw-bundles/jp/android/bundles
pjsk_body=$raw/live_pv/model/character/body/21/0001/ladies_s.bundle
motion=${CV_MOTION:-hski_all001}
motion_bundle=${CV_MOTION_BUNDLE:-$gk/dmm/octo/mot_live_chr_hski_all-001_00_in.unity3d}
scene=${CV_SCENE:-env_3d_live_all001-00-noon}
stage_bundles=${CV_STAGE_BUNDLES:-$gk/work/live_all001/pc/bundles}
stage_out=${CV_STAGE_OUT:-$work/stage/all001}
cv="$py -I $work/converter/convert.py"

sync_converter() {
  ssh $host "mkdir -p $work/data $work/out $work/stage"
  rsync -a --delete --exclude __pycache__ --exclude unity "$here/" $host:$work/converter/
}

case "${1:-}" in
  export)
    sync_converter
    ssh $host "$cv skeleton --game pjsk --bundle $pjsk_body --out $work/data/pjsk_skeleton.json &&
      $cv skeleton --game gakumas --bundle $gk/models/bundles/mdl_chr_hski-schl-0000_body.unity3d --out $work/data/gakumas_skeleton.json &&
      $cv humanoid-curves --game gakumas --bundle $motion_bundle --out $work/data/$motion --rate 120" 2>&1 | grep -v -i "warning\|version_str"
    ;;
  stage)
    sync_converter
    ssh $host "rm -rf $stage_out && $cv stage --game gakumas --bundles $stage_bundles --scene $scene --out $stage_out" 2>&1 | grep -v -i "warning\|version_str"
    ;;
  bake)
    frames=${2:-}; times=${3:-}
    ssh $host "test -d $work/unity/ProjectSettings || (cd /tmp && $unity -batchmode -nographics -quit -createProject $work/unity -logFile $work/create.log)"
    ssh $host "mkdir -p $work/unity/Assets/Editor && rm -f $work/unity/Assets/Editor/MotionBake.cs*"
    rsync -a "$here/unity/HumanoidBake/Assets/Editor/" $host:$work/unity/Assets/Editor/
    ssh $host "cd /tmp && rm -rf $work/out/$motion.* $work/out/ground_*.png && ulimit -n 65536 &&
      HB_DATA=$work/data HB_OUT=$work/out HB_MOTION=$motion HB_FRAMES=$frames HB_RENDER_TIMES=$times \
      HB_RANGE=${HB_RANGE:-} HB_TRAVEL=${HB_TRAVEL:-keep} HB_TRAVEL_SCALE=${HB_TRAVEL_SCALE:-1} \
      xvfb-run -a -s '-screen 0 1920x1080x24' $unity -batchmode -force-glcore -projectPath $work/unity \
        -executeMethod HumanoidBake.Run -logFile $work/bake.log; echo exit=\$?;
      grep -E '\[HumanoidBake\]|error CS|Exception' $work/bake.log | head -40; cat $work/out/$motion.report.txt"
    ;;
  ground)
    m=${2:-$motion}
    proj=$work/haruki3dmv
    rsync -a --delete --exclude Library --exclude Temp --exclude Logs --exclude UserSettings "$here/../../unity/Haruki3DMV/" $host:$proj/
    ssh $host "cd /tmp && rm -rf $work/ground && ulimit -n 65536 &&
      EM_BUNDLES=$raw EM_MOTION=$work/out/$m EM_OUT=$work/ground EM_RENDER=${EM_RENDER:-} EM_PROBES=${EM_PROBES:-} \
      EM_PREROLL=${EM_PREROLL:-} EM_FPS=${EM_FPS:-} \
      xvfb-run -a -s '-screen 0 1920x1080x24' $unity -batchmode -force-glcore -projectPath $proj -runTests -testPlatform PlayMode \
        -testFilter ExternalMotionGround -testResults $work/ground-results.xml -logFile $work/ground.log; echo exit=\$?;
      grep -E '\[ExternalMotion\]|error CS' $work/ground.log | head -20; grep -o 'result=\"[A-Za-z]*\"' $work/ground-results.xml | head -1;
      cat $work/ground/preroll_report.txt 2>/dev/null; ls $work/ground"
    ;;
  *) sed -n 2,13p "$0"; exit 2 ;;
esac
