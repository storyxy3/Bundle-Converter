"""haruki-humanoid-curves/0: the Humanoid (Animator) curves of a Unity clip, sampled at a fixed rate.

<prefix>.json (header: channels in Unity's Humanoid attribute order, rate, frames) + <prefix>.f32 (frames x 137 float32).
Each curve is sampled as Unity stores it (streamed: Hermite keys, dense: linear, constant), so the bake evaluates the
muscles exactly where the game would at those times.
"""
import json

import numpy as np

from . import profiles
from .humanoid import curve_names
from .unity_assets import Assets
from .unity_clip import clips

FORMAT = "haruki-humanoid-curves/0"


def export(game, bundle, prefix, rate):
    prof = profiles.load(game)
    suffix = prof.get("motion", {}).get("bodyClipSuffix", "")
    a = Assets([bundle], prof["unityVersion"])
    names = curve_names()
    for c in clips(a, lambda n: n.endswith(suffix)):
        hum = c.humanoid()
        if not hum:
            continue
        n = int(round((c.stop - c.start) * rate)) + 1
        times = c.start + np.arange(n) / rate
        data = np.zeros((n, len(names)), dtype=np.float32)
        for k in range(len(names)):
            if k not in hum:
                if names[k].endswith(".w"):
                    data[:, k] = 1.0
                continue
            data[:, k] = [c.sample(hum[k], float(x)) for x in times]
        data.tofile(prefix + ".f32")
        with open(prefix + ".json", "w") as f:
            json.dump({"format": FORMAT, "game": game, "source": str(bundle), "clip": c.name, "rate": rate, "start": c.start,
                       "stop": c.stop, "frames": n, "channels": names, "present": [k in hum for k in range(len(names))]}, f, indent=1)
        print(f"humanoid curves: {c.name} {n} frames @ {rate} Hz, {len(hum)}/{len(names)} channels")
        return
    raise SystemExit(f"no Humanoid clip ending in {suffix!r} in {bundle}")
