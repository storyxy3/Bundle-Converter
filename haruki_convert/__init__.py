"""Haruki converter: other games' / tools' content into Haruki formats for the PJSK player (tooling, not game code).

Layout
  unity_assets.py   UnityPy access shared by every Unity-game source: bundle closure, PPtr deref, transforms, meshes
  unity_clip.py     AnimationClip decoder (streamed / dense / constant curves, generic bindings)
  humanoid.py       Unity Humanoid curve and muscle names
  profiles.py       game profiles (profiles/<game>.json): skeleton conventions, humanoid maps, stage shader mapping
  skeleton.py       haruki-skeleton/0 export (any Unity body bundle + a profile)
  sources/          per source game: gakumas (Humanoid curves, stage scene), pjsk (analysis of the original data)
  inspect_stage.py  inventory of a Unity stage scene closure
Formats written: haruki-skeleton/0, haruki-humanoid-curves/0, haruki-external-stage/0; the Unity HumanoidBake project
(unity/HumanoidBake) turns Humanoid curves into haruki-pjsk-bone-curves/1. See tools/converter/README.md.
"""
