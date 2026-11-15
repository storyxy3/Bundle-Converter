"""PJSK stage materials: shader -> texture / float / colour properties set, keywords; renderer lightmap indices.
Load the shader bundles (shader/live, ...) together with the stage bundles to resolve the shader names."""
import collections

from .. import profiles
from ..unity_assets import Assets


def run(bundles):
    a = Assets(bundles, profiles.load("pjsk")["unityVersion"])
    shaders = collections.defaultdict(lambda: {"n": 0, "tex": collections.Counter(), "flt": {}, "col": {}})
    lm = collections.Counter()
    for o in a.of_type("MeshRenderer"):
        lm[o.read_typetree().get("m_LightmapIndex", -1)] += 1
    for o in a.of_type("Material"):
        t = o.read_typetree()
        name = a.shader_name(o) or f"<external {t['m_Shader']}>"
        s = shaders[name]
        s["n"] += 1
        sp = t["m_SavedProperties"]
        for e in sp["m_TexEnvs"]:
            if e[1]["m_Texture"]["m_PathID"]:
                s["tex"][e[0]] += 1
        for e in sp["m_Floats"]:
            s["flt"].setdefault(e[0], set()).add(round(e[1], 3))
        for e in sp["m_Colors"]:
            s["col"].setdefault(e[0], set()).add(tuple(round(v, 2) for v in e[1].values()))
    print("renderer lightmap index:", dict(lm))
    for name, s in sorted(shaders.items(), key=lambda x: -x[1]["n"]):
        print(f"== {name}  materials {s['n']}\n   textures: {dict(s['tex'])}\n   floats: {{{', '.join(f'{k}: {sorted(v)[:4]}' for k, v in list(s['flt'].items())[:14])}}}")
