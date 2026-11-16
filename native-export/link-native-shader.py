"""Offline native material linkage. Run after NativeActorExport, before staging."""
import json
import os
from pathlib import Path
import UnityPy
from UnityPy.files.SerializedFile import FileIdentifier

UnityPy.config.FALLBACK_UNITY_VERSION = '6000.0.77f1'
content = Path('/work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001')
shader_bundle = UnityPy.load(str(content / 'actor-shader.unity3d'))
shader = next(o for o in shader_bundle.objects if o.type.name == 'Shader' and o.read().m_ParsedForm.m_Name == 'Campus/Actor/Default')
metadata = json.loads(Path(os.environ.get('U_LINK_METADATA','/work/gakumas/live-urp-ext/.recon/task-O/actor/actor.json')).read_text())
materials = {m['name']: m for m in metadata['materials']}
output = Path(os.environ.get('U_LINK_OUTPUT','/work/motion-bake/task-U/actor-out'))
for path in output.glob('mdl*.unity3d'):
    env = UnityPy.load(str(path))
    changed = 0
    for obj in env.objects:
        if obj.type.name != 'Material':
            continue
        data = obj.read_typetree()
        if data['m_Name'] not in materials:
            raise ValueError('Unmapped material ' + data['m_Name'])
        owner = obj.assets_file
        external = FileIdentifier.__new__(FileIdentifier)
        external.path = 'archive:/' + shader.assets_file.name + '/' + shader.assets_file.name
        external.temp_empty = ''
        external.guid = bytes(16)
        external.type = 0
        owner.externals.append(external)
        data['m_Shader'] = {'m_FileID': len(owner.externals), 'm_PathID': shader.path_id}
        m = materials[data['m_Name']]
        textures = dict(data['m_SavedProperties']['m_TexEnvs'])
        for required in m['textures']:
            if not textures.get(required['property'], {}).get('m_Texture', {}).get('m_PathID'):
                raise ValueError(data['m_Name'] + ' missing native texture ' + required['property'])
        data['m_ValidKeywords'] = m['keywords']
        data['m_InvalidKeywords'] = []
        data['m_CustomRenderQueue'] = m['renderQueue']
        obj.save_typetree(data)
        changed += 1
    # The serialization shader has no runtime role after native linkage.
    for directory in env.assets:
        removed = {o.path_id for o in directory.objects.values() if o.type.name == 'Shader'}
        for obj in list(directory.objects.values()):
            if obj.type.name != 'AssetBundle':
                continue
            data = obj.read_typetree()
            table = data['m_PreloadTable']
            keep = [not (p['m_FileID'] == 0 and p['m_PathID'] in removed) for p in table]
            for entry in [v for _, v in data['m_Container']] + [data['m_MainAsset']]:
                start, size = entry['preloadIndex'], entry['preloadSize']
                entry['preloadIndex'] = sum(keep[:start])
                entry['preloadSize'] = sum(keep[start:start + size])
            data['m_PreloadTable'] = [p for p, retained in zip(table, keep) if retained]
            obj.save_typetree(data)
        for path_id in removed:
            directory.objects.pop(path_id)
    path.write_bytes(env.file.save(packer='lz4'))
    print(path.name, 'native materials', changed)

