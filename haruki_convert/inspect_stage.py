"""Inventory of a Unity stage scene closure: object types, renderers, shaders, lightmaps, vertex counts."""
import collections
from pathlib import Path

from . import profiles
from .unity_assets import Assets


def run(game, bundles_dir, scene):
    a = Assets.directory(bundles_dir, profiles.load(game)["unityVersion"])
    in_scene = a.scene_objects(Path(bundles_dir) / (scene + ".unity3d"))
    print("scene object types:", dict(collections.Counter(o.type.name for o in in_scene).most_common(25)))
    shaders, lm, meshes, verts, tris, enabled, mats = collections.Counter(), collections.Counter(), set(), 0, 0, 0, {}
    for o in in_scene:
        if o.type.name != "MeshRenderer":
            continue
        t = o.read_typetree()
        enabled += bool(t.get("m_Enabled"))
        lm[t.get("m_LightmapIndex", -1)] += 1
        go = a.deref(o, t["m_GameObject"]).read_typetree()
        mf = next((c for c in (a.deref(o, x["component"]) for x in go["m_Component"]) if c is not None and c.type.name == "MeshFilter"), None)
        mo = a.deref(mf, mf.read_typetree()["m_Mesh"]) if mf is not None else None
        if mo is not None and (mo.assets_file.name, mo.path_id) not in meshes:
            meshes.add((mo.assets_file.name, mo.path_id))
            m = mo.read_typetree()
            verts += m["m_VertexData"]["m_VertexCount"]
            tris += sum(s["indexCount"] for s in m["m_SubMeshes"]) // 3
        for mp in t["m_Materials"]:
            mo = a.deref(o, mp)
            if mo is None:
                shaders["<missing material>"] += 1
                continue
            k = (mo.assets_file.name, mo.path_id)
            mats.setdefault(k, a.shader_name(mo) or "<missing shader>")
            shaders[mats[k]] += 1
    print(f"MeshRenderers: {sum(lm.values())} (enabled {enabled}); unique meshes {len(meshes)}, vertices {verts}, triangles {tris}; materials {len(mats)}")
    print("lightmap index -> renderers:", dict(sorted(lm.items())))
    for s, n in shaders.most_common():
        print(f"   {n:5d} {s}")
    for o in in_scene:
        if o.type.name == "LightmapSettings":
            for i, l in enumerate(o.read_typetree()["m_Lightmaps"]):
                tx = a.deref(o, l.get("m_Lightmap", {}))
                if tx is not None:
                    tr = tx.read()
                    print(f"   lightmap [{i}] {tr.m_Name} {tr.m_Width}x{tr.m_Height} format {tr.m_TextureFormat}")
