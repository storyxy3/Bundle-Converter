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
