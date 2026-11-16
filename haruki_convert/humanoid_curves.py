"""Sample Humanoid channels plus authored Move and IK scales into haruki-humanoid-curves/1.

The first 137 named channels retain /0 ordering. The appended 33 scalars are Move.xyz and ten
IK locator scales.xyz. Typed Generic/component curves and metadata live in a versioned sidecar.
Streamed Hermite, dense linear and constant storage is evaluated at the requested sample times.
"""
import json

import numpy as np

from . import profiles
from .humanoid import curve_names
from .unity_assets import Assets
from .unity_clip import clips

FORMAT = "haruki-humanoid-curves/1"


def export(game, bundle, prefix, rate, layout_bundle=None, include_props=False):
    if rate <= 0: raise ValueError("rate must be positive")
    prof = profiles.load(game)
    suffix = prof.get("motion", {}).get("bodyClipSuffix", "")
    a = Assets([bundle], prof["unityVersion"])
    names = curve_names()
    for c in clips(a, lambda n: n.endswith(suffix)):
        hum = c.humanoid()
        if not hum:
            continue
        n = int(np.ceil((c.stop - c.start) * rate)) + 1
        times = np.minimum(c.start + np.arange(n) / rate, c.stop)
        data = np.zeros((n, len(names)), dtype=np.float32)
        for k in range(len(names)):
            if k not in hum:
                if names[k].endswith(".w"):
                    data[:, k] = 1.0
                continue
            data[:, k] = [c.sample(hum[k], float(x)) for x in times]
        present = [k in hum for k in range(len(names))]
        # Keep authored Move separate from normalized RootT; old bake inferred travel from Hips.
        for path, attr, label in [("Root_Body/Move", "position", "Move")] + [
                ("Root_Body/"+x, "scale", x) for x in ("IKBody", "IKGoal_LeftFoot", "IKGoal_RightFoot",
                "IKGoal_LeftHand", "IKGoal_RightHand", "IKHint_LeftKnee", "IKHint_RightKnee",
                "IKHint_LeftElbow", "IKHint_RightElbow", "LookAt")]:
            ci = c.transform(path, attr)
            vals = np.zeros((n,3), dtype=np.float32) if ci is None else np.array([
                [c.sample(ci+k, float(t)) for k in range(3)] for t in times], dtype=np.float32)
            data = np.concatenate((data, vals), axis=1)
            names.extend(label+"."+axis for axis in "xyz")
            present.extend([ci is not None]*3)
        if not np.isfinite(data).all(): raise ValueError("non-finite motion samples")
        data.astype("<f4").tofile(prefix + ".f32")
        from .motion import sidecar, flags, metadata
        sidecar(a, c, prefix, rate, times, include_props, layout_bundle)
        meta=metadata(a);base=meta.get("baseAnimation",{})
        with open(prefix + ".json", "w") as f:
            json.dump({"format": FORMAT, "game": game, "source": str(bundle), "clip": c.name, "rate": rate, "start": c.start,
                       "stop": c.stop, "frames": n, "channels": names, "present": present, "settings": flags(c), "applyPlayableIK": bool(base.get("applyPlayableIK",False)), "applyFootIK": bool(base.get("applyFootIK",False)), "isAdditive": bool(meta.get("isAdditive",False)), "hasMask": bool(base.get("mask",{}).get("m_PathID",0)), "semanticsFile": prefix.rsplit("/", 1)[-1]+".semantics.json", "layoutFile": prefix.rsplit("/", 1)[-1]+".layout.f32" if layout_bundle else ""}, f, indent=1)
        print(f"humanoid curves: {c.name} {n} frames @ {rate} Hz, {len(hum)}/137 Humanoid channels + {len(names)-137} auxiliary scalars")
        return
    raise SystemExit(f"no Humanoid clip ending in {suffix!r} in {bundle}")
