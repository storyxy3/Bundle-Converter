# Haruki converter

A conversion platform for content from other games and tools (skeletons, motions, stages; later faces, cameras, audio)
into Haruki formats the PJSK player loads. Tooling, not game code: the player never runs it.

## Shape

- **Sources** read another game's data. Unity games share `haruki_convert/unity_assets.py` (bundle closures, PPtr
  resolution, scene transforms, meshes) and `unity_clip.py` (AnimationClip curves). Game-specific readers live in
  `haruki_convert/sources/`.
- **Profiles** (`profiles/<game>.json`) hold what the converter knows about a game, outside the code: Unity version,
  skeleton root, Humanoid bone map and HumanDescription, the target's own bone conventions (roll bones, twist moves,
  travel carrier), stage shader mapping. Adding a game is mostly adding a profile and, if needed, a source reader.
- **Formats** are versioned files, so the player stays generic:

| format | written by | content |
| --- | --- | --- |
| `haruki-skeleton/0` | `convert.py skeleton` | transform hierarchy (rest pose) + Humanoid map + profile description / conventions |
| `haruki-humanoid-curves/0` | `convert.py humanoid-curves` | RootT/RootQ, IK goals, 95 muscles, sampled at a fixed rate (.json + .f32) |
| `haruki-pjsk-bone-curves/1` | `unity/HumanoidBake` | target bone local rotations + travel carrier + hip positions per frame (.json + .f32) |
| `haruki-external-stage/1` | `convert.py stage` | meshes, textures, target stage materials, renderers (stage.json + geometry.bin + textures/) |

- **Bakes that need Unity's own maths** (Humanoid muscles -> bones) run in the small Unity project
  `unity/HumanoidBake` (batch mode, `-executeMethod HumanoidBake.Run`). It builds the source and target Avatars from
  skeleton JSON (no game bundles), applies the curves with `HumanPoseHandler.SetHumanPose`, applies the target
  conventions from the target skeleton JSON, writes the bone curves, compares both rigs and renders stick figures.

## Running

`convert.py` needs UnityPy, numpy and Pillow (on JP01: `/work/gakumas/tools/venv/bin/python -I convert.py ...`).
`jp01.sh` runs the whole chain on JP01 (`export`, `stage`, `bake`, `ground`); see its header for options.
Analyses behind the PJSK profile numbers: `convert.py pjsk-twist`, `convert.py pjsk-stage-materials`.

## Notes

- PJSK: one normalized body skeleton for every figure; `Position` is `CharacterModel.PositionNote` (scaled by the
  character height, its own localPosition is not), so baked travel is multiplied by the height in the player.
- Gakumas stage lightmaps are BC6H HDR; UnityPy decodes them to 8 bits (clamped). Normal / PBR / emission maps and
  monitors are not used by the PJSK LightMap shaders yet.
- Findings and numbers: handoff/2026-11-15-prsk-stage-external-motion-plan.md.

## Task L: motion conversion in both directions (local only)

`/work/motion-bake/task-L/motion-convert.sh` contains the exact local commands.
It runs only this converter's Unity project with **6000.0.77f1**. Do not use the older
`jp01.sh` SSH/remote or test entry points for Task L.

- `generic-motion --bundle ... --skeleton ... --clip motion_0001 --out PREFIX --height 1.58`
  samples the original Generic clip, including TRS and its authored roll/assist bones.
- `HumanoidBake.Reverse` (env `HB_DATA`, `HB_OUT`, `HB_MOTION`) folds Wrist X twist back
  into Elbow while preserving wrist world orientation, then calls `GetHumanPose` on the
  PJSK Avatar with Gakumas HumanDescription. Side-branch roll bones are **not** summed
  into the chain: doing so would double the twist already present in Arm/Wrist.
- `humanoid-curves` now emits `/1`: the 137 original channels, Move.xyz, then the ten
  IK control scales.xyz. `--layout-bundle` preserves root and actor placement;
  `--include-props` retains prop associations and typed constraint curves.
- `HumanoidBake.Run` reconstructs a native editor Humanoid clip, copies supported clip
  settings, evaluates authored Generic transforms and the documented IK job order,
  calls native `SolveIK`, then applies the late Hips XZ overwrite. It retargets the
  evaluated source pose, writes authoritative Move divided by `HB_HEIGHT` (default
  1.58), and optionally bakes layout with `HB_LAYOUT=bake` (default `separate`).
- `pjsk-assists --skeleton ... --out fit.json BUNDLE...` measures quadratic fits from
  original motions, holding out the final bundle. `HB_ASSISTS=fit.json` enables these
  explicitly approximate helpers. Four additional translations require bone format
  `/2`; without helpers, the existing `/1` layout is retained.
- `motion-track --timeline ... --bundles ... --actor Actor_00 --override EXPOSED_NAME=BUNDLE --out track.json`
  resolves actual MotionDefine references and explicit scene overrides.
  `flatten-motion --track track.json --clip CLIP=BAKED_PREFIX --out PREFIX --rate 120`
  samples evaluated segments using start, clip-in, duration, time scale and source loop
  flags. Cuts are preserved; no invented in→loop sequence or crossfade is inserted.
- `motion-template --template BUNDLE --motion PREFIX [--include-props]` attaches native
  MotionDefine/body settings and all nonhuman template channels at the converted
  motion's clock. Source PPtrs remain provenance; this is not a serialized native
  MotionDefine object. Face/effect animation is excluded.
- `contact-weights --motion PREFIX --out NEW_PREFIX` optionally infers foot weights
  from sampled height and speed. This is an explicitly labelled approximation. The
  default reverse output keeps all weights zero, matching original PJSK FK.

### File contracts

`haruki-external-motion/1` is JSON + little-endian float32, **152 floats/frame**:

1. 137 named Unity channels (`MotionT/Q`, `RootT/Q`, four goal T/Q, 95 muscles).
2. `Move.xyz` in meters = source `Position * characterHeight`.
3. Four goal controls, LeftFoot/RightFoot/LeftHand/RightHand order, each position
   weight, rotation weight and pull weight.

The JSON supplies `channels`, `rate`, `frames`, `duration`, `dataFile`,
`sourceHumanScale`, `characterHeight`, `rootPolicy`, `goalSpace`, `loop` and optional
`helpersFile`/`templateSemanticsFile`. RootT is normalized body-center position and
includes Position travel: **apply it once**, without also adding Move. Muscles can
legitimately exceed ±1; do not clamp them. Goal poses are explicitly **source Avatar
root-local / sourceHumanScale**, not Unity's serialized goal space. A consumer that
cannot convert this space must reject nonzero weights. The runtime need not build
an AnimationClip: use HumanPoseHandler or a human-stream job at its live clock.

`haruki-motion-helpers/1` stores original helper TR (seven floats per named bone per
frame). Restore Elbow→Wrist convention after Humanoid application, then apply these
original helpers before physics. The selected motion has eight helpers, including
its authored ArmRoll rather than the forward direction's fitted ArmRoll rule.

`haruki-pjsk-bone-curves/2` extends `/1`: all named local quaternions, Position xyz,
Hip xyz, then localPosition xyz for each `extraPositionBones` entry. `loop`, actual
`duration`, `characterHeight`, `layoutPolicy` and `semanticsFile` are explicit.
A `/1` consumer must reject `/2`, not misread the additional positions.

`haruki-motion-semantics/1` stores typed original nonhuman channels, full compiled
binding identity, native body metadata/settings, optional props and optional layout.
It is a sampled authored-channel sidecar; original continuous coefficients are not retained. The current player does not execute arbitrary
component constraints or construct props merely because they are present here.

### Explicit limits

The IK bake uses the **source** rig/locators, then retargets its solved pose. It does
not claim exact foot/hand contacts after a change of proportions. Pull defaults
stiffness=1 / iterations=5 are source constructor defaults; env `HB_IK_STIFFNESS` /
`HB_IK_ITERATIONS` explicitly supplies runtime overrides. Animated goal positions,
rotations and weights come from source curves. Scene furniture/other locator overrides
are not reconstructed. Active hand-collision gates and LookAt require external model/
scene state and are rejected with TODO messages. Quartz/Swing/face behavior is outside
this motion-only bake. `startAtOrigin=false` is rejected if the editor cannot expose
that native setting; no guessed origin adjustment is used. Native mirror/loop/root
settings supported by AnimationUtility are applied offline and must not be applied
again by a bone consumer.

Timeline easing, overlapping layers, gaps, masks and additive clips require the
original layer graph and are explicitly rejected. The implemented segment flattener
covers consecutive `_in`/`_lp` segments with clip-in, rate, duration and loop policy;
file suffixes themselves carry no policy.

Task L actor extraction is the separate converter stage
`../actor-export/export_actor.py`, followed by the worktree's editor entry
`PjskActorExport.Run`. Its actor result documents that two-stage pipeline; it is not
silently duplicated inside the motion converter.
