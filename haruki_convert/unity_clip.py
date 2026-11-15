"""AnimationClip (Mecanim, non-legacy) decoder: streamed (Hermite keys), dense (linear) and constant curves.

Curve index order inside a clip: streamed, then dense, then constant. Generic bindings map to consecutive curve indices:
Transform (typeID 4) position 3, rotation (quaternion) 4, scale 3, euler 3; everything else (Animator 95 humanoid
curves, MonoBehaviour 114, SkinnedMeshRenderer 137 blend shapes, ...) 1.
"""
import bisect
import struct
import zlib

import numpy as np

TRANSFORM_WIDTH = {1: 3, 2: 4, 3: 3, 4: 3}
TRANSFORM_ATTR = {"position": 1, "rotation": 2, "scale": 3, "euler": 4}


def _streamed_keys(words, curve_count):
    b = struct.pack(f"<{len(words)}I", *words)
    keys = [[] for _ in range(curve_count)]
    p = 0
    while p < len(b):
        t, n = struct.unpack_from("<fi", b, p)
        p += 8
        for _ in range(n):
            idx, c0, c1, c2, v = struct.unpack_from("<i4f", b, p)
            p += 20
            keys[idx].append((t, (c0, c1, c2, v)))
    return keys


class Clip:
    def __init__(self, typetree):
        self.t = typetree
        self.name = typetree["m_Name"]
        mc = typetree["m_MuscleClip"]
        self.muscle_clip = mc
        c = mc["m_Clip"]["data"]
        self.start, self.stop = mc["m_StartTime"], mc["m_StopTime"]
        self.sample_rate = typetree["m_SampleRate"]
        self.S = c["m_StreamedClip"]["curveCount"]
        self.skeys = _streamed_keys(c["m_StreamedClip"]["data"], self.S)
        self.stimes = [[k[0] for k in ks] for ks in self.skeys]
        d = c["m_DenseClip"]
        self.D, self.dn, self.drate, self.dbegin = d["m_CurveCount"], d["m_FrameCount"], d["m_SampleRate"], d["m_BeginTime"]
        self.dense = np.array(d["m_SampleArray"], dtype=np.float32).reshape(self.dn, self.D) if self.D else np.zeros((0, 0), np.float32)
        self.const = c["m_ConstantClip"]["data"]
        self.bindings = typetree["m_ClipBindingConstant"]["genericBindings"]
        self.bind = {}
        i = 0
        for g in self.bindings:
            a, tid = g["attribute"], g["typeID"]
            self.bind[(g["path"], a, tid)] = i
            i += TRANSFORM_WIDTH.get(a, 1) if tid == 4 else 1
        self.curve_count = i

    def kind(self, ci):
        return "streamed" if ci < self.S else "dense" if ci < self.S + self.D else "const"

    def sample(self, ci, time):
        if ci < self.S:
            ks = self.skeys[ci]
            j = max(0, bisect.bisect_right(self.stimes[ci], time) - 1)
            t0, (c0, c1, c2, v) = ks[j]
            dt = time - t0
            return ((c0 * dt + c1) * dt + c2) * dt + v
        ci -= self.S
        if ci < self.D:
            f = (time - self.dbegin) * self.drate
            i = int(max(0, min(self.dn - 1, np.floor(f))))
            j = min(i + 1, self.dn - 1)
            u = max(0.0, min(1.0, f - i))
            return float(self.dense[i, ci] * (1 - u) + self.dense[j, ci] * u)
        return self.const[ci - self.D]

    def transform(self, path, attr):
        """First curve index of a Transform binding; attr = 'position' | 'rotation' | 'scale' | 'euler' (or 1..4)."""
        a = TRANSFORM_ATTR.get(attr, attr)
        return self.bind.get((zlib.crc32(path.encode()) & 0xFFFFFFFF, a, 4))

    def humanoid(self):
        """{humanoid attribute index: curve index} of the Animator (typeID 95) bindings."""
        return {g["attribute"]: self.bind[(g["path"], g["attribute"], 95)] for g in self.bindings if g["typeID"] == 95}


def clips(assets, name_filter=None):
    for o in assets.of_type("AnimationClip"):
        t = o.read_typetree()
        if name_filter is None or name_filter(t["m_Name"]):
            yield Clip(t)
