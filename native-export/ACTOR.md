# Native actor export

Use Unity 6000.0.77f1 and the existing `native-export` worktree. Copy
`NativeActorExport.cs` and `NativeMotionExport.cs` into its `Assets/Editor`,
and `NativeActorSerialization.shader` into `Assets/`. The serialization shader is
removed from the bundles by the offline linker after native shader references are written.
No runtime module is required: LiveHost's existing manifest is the injection point.
No player sources or native runtime packages are changed.

```sh
cd /work/gakumas/live-urp-native
ulimit -n 65536
unshare -n xvfb-run -a -s '-screen 0 1280x720x24' \
 /work/.toolchains/unity-6000.0.77f1/Editor/Unity \
 -batchmode -force-glcore -quit -projectPath "$PWD" \
 -executeMethod NativeActorExport.Run -logFile "$PWD/.recon/actor-repeat.log"
/work/gakumas/tools/venv/bin/python \
 /work/motion-bake/task-S/converter/native-export/link-native-shader.py
```

The actor exporter uses L's rest prefab and O's native Swing components and fitted
parameters. `S_SWING_BUNDLE` can select a replacement native Swing source bundle.
The native Temari body scaffold supplies native hierarchy, IK helper transforms,
and Quartz authoring. Mesh binding matrices compensate the source-to-native bone
mapping offline. Source offset/helper influences fold to retained ancestors;
source arm/forearm roll influences map to native Quartz roll transforms.
Hair/skirt Swing nodes form uninterrupted native chains. Source hair branches
remain separate chains; no transverse constraints are invented.

Face and hair use native `Head_Face`/`Head_Hair` part connections. The source face
is rigidly neutral on Head_Face with ordinary SkinnedMeshRenderers. Native VLSkinning
expression data is not reconstructed. A native resource bundle with empty blink
arrays accompanies this neutral-face package. The native facial-system code is
unchanged. Material properties/textures use L's mapping; the postprocessor writes
native compiled-shader references into the serialized bundles. It also preserves
the motion definition's original CAB/PathID for the timeline's direct reference. It does not replace
shaders at runtime.

Prefab filenames must contain the full native model name: Unity's main prefab
asset name comes from that filename. A plain `body.prefab` makes the host name its
root `Root_body`, breaking the native `Root_Body` bindings. Imported native scripts
must be recreated against project-local scripts before serialization: retaining a
bundle-only MonoScript emits a zero AssetDatabase GUID.

Run the motion exporter using README.md, then stage all five replacements:

```sh
python3 -B /work/motion-bake/task-S/converter/stage-native.py \
 /work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001 \
 /work/motion-bake/task-S/content-native \
 --bundle /work/motion-bake/task-S/actor-out/mdl_chr_ttmr-cstm-0003_body.unity3d \
 --bundle /work/motion-bake/task-S/actor-out/mdl_chr_ttmr-cstm-0003_hair.unity3d \
 --bundle /work/motion-bake/task-S/actor-out/mdl_chr_ttmr-base-0000_face.unity3d \
 --bundle /work/motion-bake/task-S/actor-out/trueend-resources.unity3d \
 --bundle /work/motion-bake/task-S/motion-out/mot_live_chr_ttmr_ttmr-001_00_in.unity3d
```

Build the unchanged mainline player with `LiveBuild.BuildLinux` in the same Unity
invocation pattern, then run `bash /work/motion-bake/task-S/capture-native.sh 28`
(and 45, 71), one invocation at a time. All inputs stay local; network namespaces
prevent Unity/player connections to other hosts.
