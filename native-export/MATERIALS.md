Tasks V/W offline material authoring

Read both codex/COMMON.md files first. NativeActorExport/NativeChainRestructure and player runtime sources are unchanged. This pass reads U's already-exported native bundles and writes separate variant bundles under task-W/output (historical V outputs stay under task-V). It keeps native shader references and components; no runtime adapter or custom shader is emitted.

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

Task W skin decomposition and default (offline authoring only)

The default output root is now task-W (V_ROOT still overrides it). Copy the existing V survey's ramps.json,
presets.json and mdl_chr_*.png to task-W/survey; these are read-only inputs reused from V's completed census.
The skin switch defaults to --skin-mode source: source facial ShadowTex/BaseMap linear-light median ratio,
with RGB transitioning from white to that ratio using the selected native alpha curve; native RGBA dimensions,
alpha texels, texture sampling metadata, skin masks and runtime saturation rule remain in use.
--skin-mode nearest selects V's previous nearest-native RGBA ramp unchanged. Skin OFF keeps U's constant ramp.
This is a converter authoring policy, not a recovered game method or a claim of source-render parity.

Repeat the complete decomposition (each capture retains V's ttmr001 camera/seek/frame protocol):
  PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/skin-study.py
  bash /work/motion-bake/task-U/skin-source-captures.sh
  python3 /work/motion-bake/task-U/skin-figures.py
The source capture uses task-W/source-capture.mjs and task-W/vite.config.ts with the unchanged Prsk-3D WebGL player,
loopback in a private network namespace, and source-costume master data routed in memory. Its all001 pose/scene
is a separate appearance reference, not a matched ttmr001 comparison. Runtime code is unchanged.

Generate the production default or the old switch explicitly:
  PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/material-native.py --actor ichika --variant default --enable hair,face,classes,skin,outline,eyes,mapping
  PYTHONPATH=/usr/lib/python3/dist-packages /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/material-native.py --actor miku --variant legacy-skin --enable hair,face,classes,skin,outline,eyes,mapping --skin-mode nearest
Capture a generated production variant:
  bash /work/motion-bake/task-U/material-capture.sh ichika default
Use a distinct production label (default above) to retain the study's reference assets. The study's all is V's
legacy RGBA reference; the material tool's all uses the new default source tint. The study's off means V all-minus-skin (all other passes ON); it differs from the material tool's off (all passes OFF).
Study saturation variants set the native timeline Volume skinSaturation overrides to 0 (shader multiplier 1),
instead of changing runtime code or adding an ineffective per-material property. Study mask variants restore U's
source-converted ShadeMap alpha (before V face transfer/body inference), with Miku's source-backed mapping repair.
metrics.csv uses fixed interior polygons and a fixed darkest-baseline-quartile screen-space shadow proxy; it does
not recover ramp U or an anatomical visibility mask. Source-scene deltaE values include different lighting.

The faithful mode explicitly uses the native RampMap RGBA32 format (4); this avoids re-encoding its alpha
through Miku hair's inherited compressed source template. The nearest mode retains V's previous texture output.
CPU software captures default to LP_NUM_THREADS=16; camera, quality, sample time and native runtime are unchanged.

## Task X: native skin reference and optional skin base

`skin` now fills missed pale/warm source facial texels in the transferred native
ShadeMap alpha, using the same source colour inference as body classes. This is
an inferred converter mask, not artist-labelled segmentation. Arms/legs keep their
existing masks. Native thresholds, normals, ramp alpha and saturation rule stay in
use. `--skin-mode source` still derives shadow tint from original source maps.

The opt-in `--skin-base native` maps the source skin median Lab lightness/chroma
to Temari's native body-skin median. Each source texel retains its Lab hue before
sRGB gamut clipping and rounding; source lightness variation is retained. It uses
one reference across face/body to avoid authoring a different palette per part.
This is a style policy, not recovered game code or an exact native match. The
default `--skin-base source` retains the source BaseMap. The pale/warm inference
has the same limitations as the existing body class inference.

```bash
# X survey is a local copy of W's catalogue; V_ROOT controls output location.
V_ROOT=/work/motion-bake/task-X PYTHONPATH=/usr/lib/python3/dist-packages \
 /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/material-native.py \
 --actor ichika --variant fixed --enable hair,face,classes,skin,outline,eyes,mapping \
 --skin-mode source --skin-base native
# Asset probes / captures use the existing unchanged native player:
PYTHONPATH=/usr/lib/python3/dist-packages LP_NUM_THREADS=8 \
 /work/gakumas/tools/venv/bin/python /work/motion-bake/task-U/skin-native-study.py ichika fixed
python3 /work/motion-bake/task-U/skin-native-figures.py
```
