"""How PJSK's original MV motions drive the roll bones and the stage position (the numbers in profiles/pjsk.json).

Twist = rotation about the bone's local X relative to its rest rotation. Fits ArmRoll on the Arm twist and ForeArmRoll on
the Wrist / Elbow twists by least squares; prints who carries the stage travel (Position vs Hip).
"""
import json
import math

import numpy as np

from .. import profiles
from ..unity_assets import Assets
from ..unity_clip import clips


def qmul(a, b):
    ax, ay, az, aw = a; bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def qinv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def euler_to_q(e):  # Unity Quaternion.Euler: q = qy * qx * qz
    x, y, z = [math.radians(v) / 2 for v in e]
    return qmul(qmul(np.array([0, math.sin(y), 0, math.cos(y)]), np.array([math.sin(x), 0, 0, math.cos(x)])),
                np.array([0, 0, math.sin(z), math.cos(z)]))


def twist_x(q):
    return (2 * math.degrees(math.atan2(q[0], q[3])) + 180) % 360 - 180


def run(skeleton_json, bundles):
    skel = json.load(open(skeleton_json))
    bones = skel["bones"]
    idx = {b["name"]: i for i, b in enumerate(bones)}
    rest = {b["name"]: np.array(b["rotation"]) for b in bones}

    def path_of(i):
        parts = []
        while bones[i]["parent"] >= 0:
            parts.append(bones[i]["name"]); i = bones[i]["parent"]
        return "/".join(reversed(parts))

    rows = {s: {k: [] for k in ("arm", "elbow", "wrist", "armroll", "forearmroll")} for s in ("Left", "Right")}
    pos = {"Position": [], "Hip": []}
    for bundle in bundles:
        a = Assets([bundle], profiles.load("pjsk")["unityVersion"])
        for c in clips(a, lambda n: n.startswith("motion")):
            def local_q(name, t):
                p = path_of(idx[name])
                qi = c.transform(p, "rotation")
                if qi is not None:
                    return np.array([c.sample(qi + k, t) for k in range(4)])
                ei = c.transform(p, "euler")
                return euler_to_q([c.sample(ei + k, t) for k in range(3)]) if ei is not None else rest[name]

            def local_p(name, t):
                pi = c.transform(path_of(idx[name]), "position")
                return np.array([c.sample(pi + k, t) for k in range(3)]) if pi is not None else np.array(bones[idx[name]]["position"])

            for t in np.arange(c.start, c.stop, 1 / 30):
                for s, r in rows.items():
                    for key, bone in (("arm", f"{s}_Arm"), ("elbow", f"{s}_Elbow"), ("wrist", f"{s}_Wrist"),
                                      ("armroll", f"{s}_ArmRoll"), ("forearmroll", f"{s}_ForeArmRoll")):
                        r[key].append(twist_x(qmul(qinv(rest[bone]), local_q(bone, t))))
                pos["Position"].append(local_p("Position", t)); pos["Hip"].append(local_p("Hip", t))
            print(f"{bundle}: {c.name}")
    for s, r in rows.items():
        A = {k: np.array(v) for k, v in r.items()}
        print(f"== {s}: twist std arm {A['arm'].std():.1f} elbow {A['elbow'].std():.2f} wrist {A['wrist'].std():.1f}")
        for target, feats in (("armroll", ("arm",)), ("forearmroll", ("wrist",)), ("forearmroll", ("wrist", "elbow"))):
            X = np.stack([A[f] for f in feats], 1)
            coef, *_ = np.linalg.lstsq(X, A[target], rcond=None)
            res = A[target] - X @ coef
            print(f"  {target:12s} ~ " + " + ".join(f"{v:+.3f}*{f}" for v, f in zip(coef, feats)) + f"   residual std {res.std():.2f} deg")
    P, H = np.array(pos["Position"]), np.array(pos["Hip"])
    print("Position.localPosition min", P.min(0).round(3), "max", P.max(0).round(3))
    print("Hip.localPosition      min", H.min(0).round(3), "max", H.max(0).round(3))
