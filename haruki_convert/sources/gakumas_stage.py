"""Gakumas stage scene -> haruki-external-stage/1 with the target game's stage materials (profiles/<target>.json "stage").

Format haruki-external-stage/1 (arrays only, no nulls: Unity's JsonUtility reads it). Output (out dir): stage.json (meshes, textures, materials as target shaders + properties, renderers with world TRS and
lightmap UV scale/offset), geometry.bin (per mesh: positions, normals, uv0, uv1 float32, then submesh indices uint32),
textures/*.png (albedo RGBA8 x _BaseColor); BC6H lightmaps are linear RGBAHalf .bin (bottom row first).

Material mapping (PJSK target): Environment/Default and the canvases -> stage.shaders.opaque / cutout / transparent;
main texture = albedo; lightmap texture = the scene lightmap, uv1 = lightmap UV x the renderer's scale/offset (applied by
the player per renderer); renderers without a lightmap get a neutral 4x4 lightmap. `vertexColor` carries the exposure.
Only LOD 0 of each LODGroup is kept; meshes without an index buffer are skipped (counted).
"""
import ctypes
import json
from pathlib import Path

import numpy as np
from PIL import Image
from UnityPy.helpers.MeshHelper import MeshHandler

from .. import profiles
from ..unity_clip import Clip
from ..unity_assets import Assets, Transforms, decompose

FORMAT = "haruki-external-stage/1"  # /1: JsonUtility-friendly (arrays, no null), consumed by the player


def layout_placement(bundle, unity_version):
    """Static Actor_00 placement relative to an identity layout root; reject animated origins."""
    a = Assets([bundle], unity_version)
    layouts = [o for o in a.of_type("MonoBehaviour")
               if o.read_typetree().get("baseAnimation", {}).get("clip", {}).get("m_PathID")]
    if len(layouts) != 1:
        raise ValueError("Expected one layout definition with baseAnimation.clip")
    definition = layouts[0]
    clip = Clip(a.deref(definition, definition.read_typetree()["baseAnimation"]["clip"]).read_typetree())
    origin = None
    for path in ("", "Actor_00"):
        for attr, identity in (("position", [0, 0, 0]), ("euler", [0, 0, 0]),
                               ("rotation", [0, 0, 0, 1]), ("scale", [1, 1, 1])):
            ci = clip.transform(path, attr)
            if ci is None:
                continue
            if any(clip.kind(ci + k) != "const" for k in range(len(identity))):
                raise ValueError("Layout origin must be static")
            value = [clip.sample(ci + k, clip.start) for k in range(len(identity))]
            if path == "Actor_00" and attr == "position":
                origin = value
            elif not np.allclose(value, identity):
                raise ValueError("Layout requires rotation/scale composition, unsupported")
    if origin is None:
        raise ValueError("Layout has no Actor_00 position")
    return {"origin": origin, "offset": [-v for v in origin],
            "sourceBundle": str(bundle), "sourceClip": clip.name, "actor": "Actor_00"}


def bc6h_rgba_half(t):
    """Use etcpak's bundled bcdec CPU decoder, retaining HDR (UnityPy's PIL path clamps)."""
    import etcpak
    try:
        decode = ctypes.CDLL(etcpak._etcpak_none.__file__).bcdec_bc6h_half
    except (AttributeError, OSError) as e:
        raise RuntimeError("HDR export requires etcpak with exported bcdec_bc6h_half (Linux etcpak 0.9.15)") from e
    decode.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    decode.restype = None
    w, h = t.m_Width, t.m_Height
    raw = t.get_image_data()
    bw, bh = (w + 3) // 4, (h + 3) // 4
    if len(raw) < bw * bh * 16:
        raise ValueError("Truncated BC6H base mip")
    src = ctypes.create_string_buffer(raw)
    rgb = np.empty((bh * 4, bw * 4, 3), dtype=np.float16)
    for y in range(bh):
        for x in range(bw):
            decode(ctypes.addressof(src) + (y * bw + x) * 16,
                   rgb.ctypes.data + (y * 4 * bw * 4 + x * 4) * 6, bw * 4 * 3, 0)
    rgba = np.ones((h, w, 4), dtype="<f2")
    rgba[..., :3] = rgb[:h, :w]
    return rgba


def export(bundles_dir, scene, out, target="pjsk", layout_bundle=None):
    src = profiles.load("gakumas")
    tgt = profiles.load(target)["stage"]
    bdir, out = Path(bundles_dir), Path(out)
    (out / "textures").mkdir(parents=True, exist_ok=True)
    a = Assets.directory(bdir, src["unityVersion"])
    tf = Transforms(a)
    in_scene = a.scene_objects(bdir / (scene + ".unity3d"))

    lower_lod = set()
    for o in in_scene:
        if o.type.name == "LODGroup":
            for li, lod in enumerate(o.read_typetree()["m_LODs"]):
                if li:
                    for r in lod["renderers"]:
                        ro = a.deref(o, r["renderer"])
                        if ro is not None:
                            lower_lod.add((ro.assets_file.name, ro.path_id))

    textures, tex_index = [], {}

    def add_texture(img, base, entry):
        name = f"{len(textures):03d}_{base}.png"
        img.save(out / "textures" / name, optimize=True)
        entry = {"file": "textures/" + name, "width": img.width, "height": img.height, **entry}
        textures.append(entry)
        return len(textures) - 1

    def texture(tobj, tint):
        key = (tobj.assets_file.name, tobj.path_id, "srgb", tuple(tint))
        if key not in tex_index:
            t = tobj.read()
            img = t.image.convert("RGBA")
            if any(abs(c - 1) > 1e-3 for c in tint[:3]):
                arr = np.asarray(img).astype(np.float32)
                arr[..., :3] *= np.array(tint[:3])
                img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
            tex_index[key] = add_texture(img, t.m_Name, {"colorSpace": "srgb"})
        return tex_index[key]

    def lightmap_texture(tobj):
        key = (tobj.assets_file.name, tobj.path_id, "lightmap")
        if key not in tex_index:
            t = tobj.read()
            if t.m_TextureFormat != 24:
                raise ValueError(f"Unsupported lightmap encoding {t.m_TextureFormat}; expected PC BC6H")
            rgba = bc6h_rgba_half(t)
            arr = rgba[..., :3].astype(np.float32)
            stats = {"p50": float(np.percentile(arr, 50)), "p99": float(np.percentile(arr, 99)),
                     "max": float(arr.max()), "aboveOne": float((arr > 1).mean())}
            name = f"textures/{len(textures):03d}_{t.m_Name}.rgba16f.bin"
            (out / name).write_bytes(rgba.tobytes())
            tex_index[key] = len(textures)
            textures.append({"file": name, "width": t.m_Width, "height": t.m_Height,
                             "encoding": "rgba16f", "colorSpace": "linear", "lightmap": True,
                             "decode": "bcdec-unsigned-bc6h", "stats": stats})
        return tex_index[key]

    neutral = []

    def neutral_lightmap():
        if not neutral:
            neutral.append(add_texture(Image.new("RGB", (4, 4), (128, 128, 128)), "neutral_lightmap", {"colorSpace": "linear", "lightmap": True}))
        return neutral[0]

    scene_lightmaps = []
    for o in in_scene:
        if o.type.name == "LightmapSettings":
            for l in o.read_typetree()["m_Lightmaps"]:
                lo = a.deref(o, l.get("m_Lightmap", {}))
                scene_lightmaps.append(lightmap_texture(lo) if lo is not None else None)

    meshes, mesh_index = [], {}
    geo = open(out / "geometry.bin", "wb")

    def mesh(mo):
        key = (mo.assets_file.name, mo.path_id)
        if key in mesh_index:
            return mesh_index[key]
        m = mo.read()
        h = MeshHandler(m)
        h.process()
        n = h.m_VertexCount

        def channel(values, width, fill=None):
            return fill if not values else np.asarray(values, dtype=np.float32).reshape(n, -1)[:, :width]

        if h.m_IndexBuffer is None:
            mesh_index[key] = None
            print(f"  mesh {m.m_Name}: no index buffer, skipped")
            return None
        pos = channel(h.m_Vertices, 3)
        nrm = channel(h.m_Normals, 3, np.zeros((n, 3), np.float32))
        uv0 = channel(h.m_UV0, 2, np.zeros((n, 2), np.float32))
        uv1 = channel(h.m_UV1, 2, None)
        if uv1 is None:
            uv1 = uv0.copy()
        entry = {"name": m.m_Name, "vertexCount": n, "offset": geo.tell(), "hasUv1": bool(h.m_UV1), "submeshes": []}
        for arr in (pos, nrm, uv0, uv1):
            geo.write(arr.astype("<f4").tobytes())
        for sub in h.get_triangles():
            idx = np.asarray(sub, dtype=np.uint32).reshape(-1)
            entry["submeshes"].append({"offset": geo.tell(), "indexCount": int(idx.size)})
            geo.write(idx.astype("<u4").tobytes())
        mesh_index[key] = len(meshes)
        meshes.append(entry)
        return mesh_index[key]

    materials, mat_index = [], {}

    def material(mo, lightmapped):
        key = (mo.assets_file.name, mo.path_id, lightmapped)
        if key in mat_index:
            return mat_index[key]
        mt = mo.read_typetree()
        sp = mt["m_SavedProperties"]
        texs = {e[0]: e[1] for e in sp["m_TexEnvs"]}
        floats = {e[0]: e[1] for e in sp["m_Floats"]}
        colors = {e[0]: e[1] for e in sp["m_Colors"]}
        kws = set((mt.get("m_ValidKeywords") or []) + (mt.get("m_ShaderKeywords", "") or "").split())
        base = colors.get("_BaseColor") or colors.get("_Color") or {"r": 1, "g": 1, "b": 1, "a": 1}
        tint = [base["r"], base["g"], base["b"], base["a"]]
        albedo = None
        for name in ("_BaseMap", "_MainTex"):
            if name in texs:
                to = a.deref(mo, texs[name]["m_Texture"])
                if to is not None:
                    albedo = texture(to, tint)
                    break
        transparent = floats.get("_Surface", 0) >= 0.5 or "_SURFACE_TYPE_TRANSPARENT" in kws
        cutout = floats.get("_AlphaClip", 0) >= 0.5 or "_ALPHATEST_ON" in kws
        shader = tgt["shaders"]["transparent" if transparent else "cutout" if cutout else "opaque"]
        entry = {"name": mt["m_Name"], "sourceShader": a.shader_name(mo) or "<missing>", "shader": shader,
                 "textures": [{"property": tgt["mainTexture"], "texture": albedo}] if albedo is not None else [],
                 "color": tint if albedo is None else [1, 1, 1, 1],
                 "lightmap": "scene" if lightmapped else "neutral",
                 "floats": [{"property": "_Cutoff", "value": floats.get("_Cutoff", 0.5)}] if cutout else [],
                 "renderQueue": mt.get("m_CustomRenderQueue", -1), "sourceKeywords": sorted(kws)}
        mat_index[key] = len(materials)
        materials.append(entry)
        return mat_index[key]

    renderers, skipped = [], {"lod": 0, "disabled": 0, "nomesh": 0, "badmesh": 0}
    for o in in_scene:
        if o.type.name != "MeshRenderer":
            continue
        if (o.assets_file.name, o.path_id) in lower_lod:
            skipped["lod"] += 1
            continue
        t = o.read_typetree()
        go = a.deref(o, t["m_GameObject"])
        gt = go.read_typetree()
        if not t.get("m_Enabled") or not gt.get("m_IsActive", True):
            skipped["disabled"] += 1
            continue
        comps = [a.deref(go, c["component"]) for c in gt["m_Component"]]
        mf = next((c for c in comps if c is not None and c.type.name == "MeshFilter"), None)
        tobj = next((c for c in comps if c is not None and c.type.name == "Transform"), None)
        mo = a.deref(mf, mf.read_typetree()["m_Mesh"]) if mf is not None else None
        if mo is None:
            skipped["nomesh"] += 1
            continue
        lmi = t.get("m_LightmapIndex", 65535)
        lightmapped = lmi < len(scene_lightmaps) and scene_lightmaps[lmi] is not None
        so = t["m_LightmapTilingOffset"] if lightmapped else {"x": 1, "y": 1, "z": 0, "w": 0}
        pos, rot, scl = decompose(tf.world(tobj))
        mi = mesh(mo)
        if mi is None:
            skipped["badmesh"] += 1
            continue
        renderers.append({"name": gt["m_Name"], "position": pos, "rotation": rot, "scale": scl, "mesh": mi,
                          "materials": [material(a.deref(o, mp), lightmapped) if a.deref(o, mp) is not None else -1 for mp in t["m_Materials"]],
                          "lightmap": scene_lightmaps[lmi] if lightmapped else neutral_lightmap(),
                          "lightmapScaleOffset": [so["x"], so["y"], so["z"], so["w"]] if lightmapped else [1, 1, 0, 0],
                          "layer": gt.get("m_Layer", 0)})
    geo.close()

    doc = {"format": FORMAT, "source": {"game": "gakumas", "scene": scene, "bundles": str(bdir)}, "target": target,
           "units": "metres, Unity left-handed, stage origin = scene origin",
           "vertexColor": tgt["vertexColor"], "lightmapUv": tgt["lightmapUv"], "lightmapTexture": tgt["lightmapTexture"],
           "note": tgt.get("note", ""),
           "textures": textures, "materials": materials, "meshes": meshes, "renderers": renderers, "skipped": skipped}
    if layout_bundle is not None:
        doc["placement"] = layout_placement(layout_bundle, src["unityVersion"])
    (out / "stage.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    size = (out / "geometry.bin").stat().st_size
    print(f"stage: {len(renderers)} renderers (skipped {skipped}), {len(meshes)} meshes, {sum(m['vertexCount'] for m in meshes)} vertices, "
          f"{len(materials)} materials, {len(textures)} textures; geometry {size / 1e6:.1f} MB")
