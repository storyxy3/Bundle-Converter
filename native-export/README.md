# Native motion export

Copy NativeMotionExport.cs into Assets/Editor of the native-export worktree.
This file is editor-only; no runtime adapter is installed.

From /work/gakumas/live-urp-native:

```sh
ulimit -n 65536
unshare -n env \
 S_TEMPLATE_SEMANTICS=/work/motion-bake/task-L/motion-data/hski_all001_complete.semantics.json \
 S_MOTION=/work/motion-bake/task-L/motion-out/motion_0001.gakumas.json \
 S_CONTENT=/work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001 \
 S_OUT=/work/motion-bake/task-S/motion-out \
 xvfb-run -a -s '-screen 0 1280x720x24' \
 /work/.toolchains/unity-6000.0.77f1/Editor/Unity \
 -batchmode -force-glcore -quit -projectPath "$PWD" \
 -executeMethod NativeMotionExport.Run -logFile "$PWD/.recon/motion-repeat.log"
```

After exporting both actor and motion, run `link-native-shader.py` before staging.
It restores the native motion CAB and definition PathID referenced directly by
the original ttmr timeline, preserves the original compiled actor shader reference,
and emits the native neutral-blink resource data. See ACTOR.md for staging and captures.

Generic constants come from hski_all001; ActorMotionDefine metadata comes from
ttmr001. Source helper channels are omitted; the actor instead uses the native
body scaffold and its Quartz authoring. Nonzero source IK is rejected. Neutral
face output freezes any exposed template face curves at time zero; source PJSK
expressions are outside scope. All conversion happens offline.
