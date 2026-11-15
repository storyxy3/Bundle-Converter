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
    s = sub.add_parser("humanoid-curves"); s.add_argument("--game", required=True); s.add_argument("--bundle", required=True); s.add_argument("--out", required=True); s.add_argument("--rate", type=int, default=120)
    s = sub.add_parser("stage"); s.add_argument("--game", required=True); s.add_argument("--bundles", required=True); s.add_argument("--scene", required=True); s.add_argument("--out", required=True); s.add_argument("--target", default="pjsk")
    s = sub.add_parser("inspect-stage"); s.add_argument("--game", required=True); s.add_argument("--bundles", required=True); s.add_argument("--scene", required=True)
    s = sub.add_parser("pjsk-twist"); s.add_argument("--skeleton", required=True); s.add_argument("bundles", nargs="+")
    s = sub.add_parser("pjsk-stage-materials"); s.add_argument("bundles", nargs="+")
    a = p.parse_args()
    if a.cmd == "skeleton":
        from haruki_convert import skeleton; skeleton.export(a.game, a.bundle, a.out, a.root)
    elif a.cmd == "humanoid-curves":
        from haruki_convert import humanoid_curves; humanoid_curves.export(a.game, a.bundle, a.out, a.rate)
    elif a.cmd == "stage":
        from haruki_convert.sources import gakumas_stage
        if a.game != "gakumas":
            raise SystemExit("stage sources: gakumas")
        gakumas_stage.export(a.bundles, a.scene, a.out, a.target)
    elif a.cmd == "inspect-stage":
        from haruki_convert import inspect_stage; inspect_stage.run(a.game, a.bundles, a.scene)
    elif a.cmd == "pjsk-twist":
        from haruki_convert.sources import pjsk_twist; pjsk_twist.run(a.skeleton, a.bundles)
    elif a.cmd == "pjsk-stage-materials":
        from haruki_convert.sources import pjsk_stage_materials; pjsk_stage_materials.run(a.bundles)


if __name__ == "__main__":
    main()
