"""Offline native material linkage. Run after NativeActorExport, before staging."""
import json
from pathlib import Path
import UnityPy
from UnityPy.files.SerializedFile import FileIdentifier

UnityPy.config.FALLBACK_UNITY_VERSION = '6000.0.77f1'
content = Path('/work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001')
shader_bundle = UnityPy.load(str(content / 'actor-shader.unity3d'))
shader = next(o for o in shader_bundle.objects if o.type.name == 'Shader' and o.read().m_ParsedForm.m_Name == 'Campus/Actor/Default')
metadata = json.loads(Path('/work/gakumas/live-urp-ext/.recon/task-O/actor/actor.json').read_text())
materials = {m['name']: m for m in metadata['materials']}
output = Path('/work/motion-bake/task-S/actor-out')
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

# Native timeline assets reference this definition by CAB identity and PathID.
# Preserve the original public object identity while replacing its native payload.
motion_name = 'mot_live_chr_ttmr_ttmr-001_00_in.unity3d'
original_motion = UnityPy.load(str(content / motion_name))
template_define = next(o for o in original_motion.objects if o.type.name == 'MonoBehaviour' and 'baseAnimation' in o.read_typetree())
motion_path = output.parent / 'motion-out' / motion_name
motion = UnityPy.load(str(motion_path))
define = next(o for o in motion.objects if o.type.name == 'MonoBehaviour' and 'baseAnimation' in o.read_typetree())
old_id, new_id = define.path_id, template_define.path_id
directory = define.assets_file

def remap(value):
    if isinstance(value, dict):
        if value.get('m_FileID') == 0 and value.get('m_PathID') == old_id:
            value['m_PathID'] = new_id
        for child in value.values():
            remap(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            remap(child)

for obj in list(directory.objects.values()):
    data = obj.read_typetree()
    remap(data)
    if obj.type.name == 'AssetBundle':
        native_container = next(o for o in original_motion.objects if o.type.name == 'AssetBundle').read_typetree()['m_Container']
        native_key = next(name for name, entry in native_container if entry['asset']['m_PathID'] == new_id)
        data['m_Container'] = [(native_key, entry) for _, entry in data['m_Container']]
    if obj == define:
        data['m_Name'] = template_define.read_typetree()['m_Name']
    obj.save_typetree(data)
directory.objects.pop(old_id)
define.path_id = new_id
directory.objects[new_id] = define
if len(motion.file.files) != 1:
    raise ValueError('Unexpected external motion stream: identity relocation required')
directory.name = template_define.assets_file.name
motion.file.files = {directory.name: directory}
motion_path.write_bytes(motion.file.save(packer='lz4'))
print('Native timeline motion identity', directory.name, new_id)

# Neutral face contract: retain native facial-system code, provide no blink channels.
# PJSK expression conversion is outside this task; empty native arrays are valid data.
resources = UnityPy.load(str(content / 'trueend-resources.unity3d'))
neutralized = 0
for obj in resources.objects:
    if obj.type.name != 'MonoBehaviour':
        continue
    data = obj.read_typetree()
    if data.get('m_Name') == 'VLActorEyeBlinkData':
        data['blinkDatas'] = []
        data['limitDatas'] = []
        obj.save_typetree(data)
        neutralized += 1
if neutralized != 1:
    raise ValueError('Expected one native eye blink definition')
(output / 'trueend-resources.unity3d').write_bytes(resources.file.save(packer='lz4'))
print('Native neutral blink definitions', neutralized)
