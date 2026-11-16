Task V offline material authoring

Read both codex/COMMON.md files first. NativeActorExport/NativeChainRestructure and player runtime sources are unchanged. This pass reads U's already-exported native bundles and writes separate variant bundles under task-V/output. It keeps native shader references and components; no runtime adapter or custom shader is emitted.

Dependencies: existing Gakumas Python venv (UnityPy, Pillow, NumPy) and system SciPy via PYTHONPATH=/usr/lib/python3/dist-packages. No dependency installation required.

Survey (read-only native input; each writes only beside its script):
  /work/gakumas/tools/venv/bin/python /work/motion-bake/task-V/survey/materials.py
  /work/gakumas/tools/venv/bin/python /work/motion-bake/task-V/survey/meshes.py
  /work/gakumas/tools/venv/bin/python /work/motion-bake/task-V/survey/ramps.py
  /work/gakumas/tools/venv/bin/python /work/motion-bake/task-V/survey/highlights.py

Generate all-on / all-off / leave-one-switch-out variants:
  bash /work/motion-bake/task-U/material-batch.sh
One arbitrary combination (switches independent CLI inputs):
  PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/material-native.py --actor miku --variant selected --enable mapping,face,hair,skin
Actors: ichika, miku. Switches: hair, face, classes, skin, outline, eyes, mapping. The mapping switch repairs U's empty Miku source textures, expands source palettes when masked, restores texture scale/offset and native material contracts. Miku hair/face shader features need their proper mapping; leave-one-out captures retain mapping for those comparisons.

Output root can be changed with V_ROOT; U inputs with V_U_ROOT. Survey/presets.json and survey/ramps.json plus their PNGs must exist under V_ROOT. Native donors are mdl_chr_ttmr-{cstm-0003_body,cstm-0003_hair,base-0000_face} under /work/gakumas/models/bundles. Native material semantics are documented in gakumas/RENDERING.md section 6. All heuristics in this pass are converter policy, not recovered game methods.

Capture (stage only into the variant's own content directory; never overwrite an active capture's content):
  bash /work/motion-bake/task-U/material-captures.sh
  python3 /work/motion-bake/task-U/material-figures.py
Uses the original /work/gakumas/live-urp-native/Build/Linux/TrueEnd.x86_64 and native ttmr001 motion, 27.8 s seek, 28 s capture, 60 Hz, unchanged native camera. Original Temari image/log are copied from U/captures/native/28, at the same actual time. All-minus-switch vs all-on comparisons hold every other switch constant. Off is U's original exported baseline. Wide screenshots have 3x face/hair crops; source pixels are only cropped/enlarged, never synthesized.

Surveys distinguish shader types and proxy region labels. Skin is native ShadeMap alpha. Native metal/leather proxy labels use DefMap B/G. Source material classification uses skin alpha, RGB brightness/chroma and local contrast; colour cannot identify physical material reliably. Source Miku lacks the newer skin ValueTex mask, so warm pale pixels supply a documented converter skin-colour inference. Hair highlight bands use native row profile, source UV-to-height direction and active hair-vertex base-colour samples; this is not per-strand grooming reconstruction. Face and eye correspondences normalize mesh bounds; they are not an anatomical registration solution. One ramp is selected from facial skin samples and shared across body/hair/face. Proxy distances and per-material choices are in each output/report.json.

Compile-only check, no tests:
  ulimit -n 65536
  DOTNET_USE_POLLING_FILE_WATCHER=1 unshare -n xvfb-run -a -s '-screen 0 1280x720x24' /work/.toolchains/unity-6000.0.77f1/Editor/Unity -batchmode -force-glcore -quit -projectPath /work/motion-bake/task-U/project -logFile /work/motion-bake/task-V/compile.log

Generated textures copy native per-slot colour-space and sampler settings; DefMap data stays linear. Face authoring transfers the native ShadeMap skin alpha as well as DefMap channels. Body class authoring infers missing skin alpha from warm source colours; hair always uses the native hair G/B/A preset. Eye defaults use native eye-class channel medians. Native RampAdd is enabled only by its authoring pass; unrelated sweat layers remain disabled.

Miku mapping also routes connected static hair-cap charts from U's face mesh to its existing hair mesh. Seeds use source hair chroma, existing hair boundaries and the native eye-proxy band; warm skin and native eye classes are protected. Original face correspondence bounds are retained so routing does not change eye classification. Mesh indices and bounds change; vertices, bind poses and skin weights do not. Current result moves 725 triangles.
