"""haruki-skeleton/0: a Unity body prefab's transform hierarchy (rest pose) + the game profile's humanoid map.

Every transform from the root, depth first: name, parent index, rest local position / rotation / scale. `human` maps
bones to Unity HumanBodyBones names (for BuildHumanAvatar); `description` and `conventions` come from the profile.
"""
import json

from . import profiles
from .unity_assets import Assets, transform_hierarchy

FORMAT = "haruki-skeleton/0"


def flatten(tr, name, root_pid):
    out = []

    def walk(pid, parent):
        t = tr[pid]
        p, q, s = t.m_LocalPosition, t.m_LocalRotation, t.m_LocalScale
        idx = len(out)
        out.append({"name": name[pid], "parent": parent, "position": [p.x, p.y, p.z],
                    "rotation": [q.x, q.y, q.z, q.w], "scale": [s.x, s.y, s.z]})
        for c in t.m_Children:
            if c.path_id in tr:
                walk(c.path_id, idx)

    walk(root_pid, -1)
    return out


def export(game, bundle, out, root=None):
    prof = profiles.load(game)
    sk = prof["skeleton"]
    a = Assets([bundle], prof["unityVersion"])
    tr, name, roots = transform_hierarchy(a, root or sk.get("root"))
    if not roots:
        raise SystemExit(f"root {root or sk.get('root')!r} not found in {bundle}")
    bones = flatten(tr, name, roots[0])
    names = {b["name"] for b in bones}
    doc = {"format": FORMAT, "game": game, "source": str(bundle), "root": name[roots[0]], "rig": sk.get("rig"),
           "bones": bones,
           "human": [{"bone": b, "humanName": h} for b, h in sk["humanBones"] if b in names],
           "missingHuman": [b for b, _ in sk["humanBones"] if b not in names]}
    if "humanDescription" in sk:
        doc["description"] = sk["humanDescription"]
    if "conventions" in prof:
        doc["conventions"] = prof["conventions"]
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
    print(f"{game} skeleton: root {doc['root']}, {len(bones)} transforms, {len(doc['human'])} human bones, missing {doc['missingHuman']}")
