#!/usr/bin/env python3
"""Haruki converter command line (tooling). Run with a Python that has UnityPy + numpy + Pillow, e.g. on JP01:
  /work/gakumas/tools/venv/bin/python -I tools/converter/convert.py <command> ...

  skeleton         --game G --bundle BODY.bundle --out SKELETON.json [--root NAME]
  humanoid-curves  --game G --bundle MOTION.bundle --out PREFIX [--rate 120]
  stage            --game G --bundles DIR --scene SCENE --out DIR [--target pjsk]
  inspect-stage    --game G --bundles DIR --scene SCENE
  pjsk-twist       --skeleton PJSK_SKELETON.json CHARACTER_TIMELINE.bundle...
  pjsk-stage-materials STAGE.bundle...
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script directory


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("skeleton"); s.add_argument("--game", required=True); s.add_argument("--bundle", required=True); s.add_argument("--out", required=True); s.add_argument("--root")
    s = sub.add_parser("humanoid-curves"); s.add_argument("--game", required=True); s.add_argument("--bundle", required=True); s.add_argument("--out", required=True); s.add_argument("--rate", type=int, default=120); s.add_argument("--layout-bundle"); s.add_argument("--include-props", action="store_true"); s.add_argument("--bake-layout", action="store_true", help="Opt in to baking source stage placement into the motion (requires --layout-bundle)")
    s = sub.add_parser("stage"); s.add_argument("--game", required=True); s.add_argument("--bundles", required=True); s.add_argument("--scene", required=True); s.add_argument("--out", required=True); s.add_argument("--target", default="pjsk"); s.add_argument("--layout-bundle", help="Static Actor_00 layout defining the performance origin")
    s = sub.add_parser("inspect-stage"); s.add_argument("--game", required=True); s.add_argument("--bundles", required=True); s.add_argument("--scene", required=True)
    s = sub.add_parser("pjsk-twist"); s.add_argument("--skeleton", required=True); s.add_argument("bundles", nargs="+")
    s = sub.add_parser("pjsk-stage-materials"); s.add_argument("bundles", nargs="+")
    s = sub.add_parser("generic-motion"); s.add_argument("--bundle", required=True); s.add_argument("--skeleton", required=True); s.add_argument("--out", required=True); s.add_argument("--clip", required=True); s.add_argument("--rate", type=int, default=60); s.add_argument("--height", type=float, default=1.58)
    s = sub.add_parser("motion-track"); s.add_argument("--timeline", required=True); s.add_argument("--bundles", nargs="+", required=True); s.add_argument("--actor", default="Actor_00"); s.add_argument("--out", required=True); s.add_argument("--override",action="append",default=[])
    s = sub.add_parser("flatten-motion"); s.add_argument("--track", required=True); s.add_argument("--clip", action="append", required=True); s.add_argument("--out", required=True); s.add_argument("--rate",type=int,default=120)
    s = sub.add_parser("motion-template"); s.add_argument("--template", required=True); s.add_argument("--motion", required=True); s.add_argument("--include-props",action="store_true")
    s = sub.add_parser("pjsk-assists"); s.add_argument("--skeleton", required=True); s.add_argument("--out", required=True); s.add_argument("bundles", nargs="+")
    s = sub.add_parser("contact-weights"); s.add_argument("--motion", required=True); s.add_argument("--out", required=True); s.add_argument("--height-threshold",type=float,default=.03); s.add_argument("--speed-threshold",type=float,default=.15)
    s = sub.add_parser("live-music", help="Unity AudioClip to audio-file/1")
    s.add_argument("--bundle", required=True); s.add_argument("--out", required=True)
    s.add_argument("--vgmstream", default="vgmstream-cli")
    s.add_argument("--deobfuscator"); s.add_argument("--bundle-name")
    a = p.parse_args()
    if a.cmd == "contact-weights":
        from haruki_convert.motion import contacts; contacts(a.motion,a.out,a.height_threshold,a.speed_threshold)
    elif a.cmd == "motion-track":
        from haruki_convert.motion import track; track(a.timeline,a.bundles,a.actor,a.out,a.override)
    elif a.cmd == "flatten-motion":
        from haruki_convert.motion import flatten; flatten(a.track,a.clip,a.out,a.rate)
    elif a.cmd == "motion-template":
        from haruki_convert.motion import attach_template; attach_template(a.template,a.motion,a.include_props)
    elif a.cmd == "pjsk-assists":
        from haruki_convert.sources.pjsk_assists import run; run(a.skeleton,a.bundles,a.out)
    elif a.cmd == "generic-motion":
        from haruki_convert.motion import generic; generic(a.bundle, a.skeleton, a.out, a.clip, a.rate, a.height)
    elif a.cmd == "live-music":
        from haruki_convert import live_music
        live_music.export(a.bundle, a.out, a.vgmstream, a.deobfuscator, a.bundle_name)
    elif a.cmd == "skeleton":
        from haruki_convert import skeleton; skeleton.export(a.game, a.bundle, a.out, a.root)
    elif a.cmd == "humanoid-curves":
        from haruki_convert import humanoid_curves; humanoid_curves.export(a.game, a.bundle, a.out, a.rate, a.layout_bundle, a.include_props, a.bake_layout)
    elif a.cmd == "stage":
        from haruki_convert.sources import gakumas_stage
        if a.game != "gakumas":
            raise SystemExit("stage sources: gakumas")
        gakumas_stage.export(a.bundles, a.scene, a.out, a.target, a.layout_bundle)
    elif a.cmd == "inspect-stage":
        from haruki_convert import inspect_stage; inspect_stage.run(a.game, a.bundles, a.scene)
    elif a.cmd == "pjsk-twist":
        from haruki_convert.sources import pjsk_twist; pjsk_twist.run(a.skeleton, a.bundles)
    elif a.cmd == "pjsk-stage-materials":
        from haruki_convert.sources import pjsk_stage_materials; pjsk_stage_materials.run(a.bundles)


if __name__ == "__main__":
    main()
