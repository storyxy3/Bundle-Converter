"""UnityPy access shared by the Unity-game sources: closures of bundles, PPtr resolution, scene objects, transforms."""
import math
import warnings
from pathlib import Path

warnings.simplefilter("ignore")
import numpy as np
import UnityPy
import UnityPy.config


class Assets:
    """Every object of a set of bundles, addressable by (serialized file, path id); PPtrs resolve across files."""

    def __init__(self, paths, unity_version):
        UnityPy.config.FALLBACK_UNITY_VERSION = unity_version
        self.paths = [str(p) for p in paths]
        self.env = UnityPy.load(*self.paths)
        self.objs = {(o.assets_file.name.lower(), o.path_id): o for o in self.env.objects}

    @classmethod
    def directory(cls, bundles_dir, unity_version, pattern="*.unity3d"):
        return cls(sorted(Path(bundles_dir).glob(pattern)), unity_version)

    def deref(self, o, pptr):
        if not pptr or not pptr.get("m_PathID"):
            return None
        fid = pptr["m_FileID"]
        fn = o.assets_file.name if fid == 0 else o.assets_file.externals[fid - 1].path.split("/")[-1]
        return self.objs.get((fn.lower(), pptr["m_PathID"]))

    def of_type(self, type_name):
        return [o for o in self.env.objects if o.type.name == type_name]

    def scene_objects(self, scene_bundle_path):
        """Objects of the scene file(s) inside one scene bundle (not its .sharedAssets)."""
        sf = UnityPy.load(str(scene_bundle_path))
        cabs = {n.lower() for f in sf.files.values() for n in getattr(f, "files", {})} | {n.lower() for n in sf.files}
        return [o for o in self.env.objects
                if o.assets_file.name.lower() in cabs and not o.assets_file.name.lower().endswith(".sharedassets")]

    def shader_name(self, material_obj):
        t = material_obj.read_typetree()
        so = self.deref(material_obj, t["m_Shader"])
        try:
            return so.read().m_ParsedForm.m_Name if so is not None else None
        except Exception:
            return None


def quat_matrix(x, y, z, w):
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class Transforms:
    """World matrices of scene / prefab Transforms (cached)."""

    def __init__(self, assets):
        self.a = assets
        self.cache = {}

    def world(self, tobj):
        k = (tobj.assets_file.name, tobj.path_id)
        if k not in self.cache:
            t = tobj.read_typetree()
            p, q, s = t["m_LocalPosition"], t["m_LocalRotation"], t["m_LocalScale"]
            m = np.eye(4)
            m[:3, :3] = quat_matrix(q["x"], q["y"], q["z"], q["w"]) * np.array([s["x"], s["y"], s["z"]])
            m[:3, 3] = [p["x"], p["y"], p["z"]]
            parent = self.a.deref(tobj, t["m_Father"])
            self.cache[k] = m if parent is None else self.world(parent) @ m
        return self.cache[k]


def decompose(m):
    """World matrix -> position, rotation (x, y, z, w), lossy scale (no shear)."""
    t = m[:3, 3].tolist()
    sx, sy, sz = (float(np.linalg.norm(m[:3, i])) for i in range(3))
    r = m[:3, :3] / np.array([sx, sy, sz])
    if np.linalg.det(r) < 0:
        sx = -sx
        r[:, 0] = -r[:, 0]
    w = math.sqrt(max(0, 1 + r[0, 0] + r[1, 1] + r[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0, 1 + r[0, 0] - r[1, 1] - r[2, 2])) / 2, r[2, 1] - r[1, 2])
    y = math.copysign(math.sqrt(max(0, 1 - r[0, 0] + r[1, 1] - r[2, 2])) / 2, r[0, 2] - r[2, 0])
    z = math.copysign(math.sqrt(max(0, 1 - r[0, 0] - r[1, 1] + r[2, 2])) / 2, r[1, 0] - r[0, 1])
    return t, [x, y, z, w], [sx, sy, sz]


def transform_hierarchy(assets, root_name=None):
    """(transforms by path id, names, root path ids) of the prefab hierarchies in the loaded bundles."""
    tr = {o.path_id: o.read() for o in assets.of_type("Transform")}
    name = {pid: t.m_GameObject.read().m_Name for pid, t in tr.items()}
    roots = [pid for pid, t in tr.items() if t.m_Father.path_id not in tr]
    if root_name is not None:
        roots = [pid for pid in roots if name[pid] == root_name]
    return tr, name, roots
