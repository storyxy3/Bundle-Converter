# Native character skin-ramp catalogue. Preserve original RGBA ramp pixels.
import pathlib,json,warnings
import numpy as np,UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1';warnings.simplefilter('ignore');root=pathlib.Path(__file__).parent;rows=[];seen=set()
for p in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*_face.unity3d')):
 char=p.name.split('-')[0]
 if char in seen:continue
 e=UnityPy.load(str(p))
 for o in e.objects:
  if o.type.name!='Material':continue
  d=o.read_typetree();sp=d['m_SavedProperties']
  if dict(sp['m_Floats']).get('_ShaderType')!=9:continue
  ts=dict(sp['m_TexEnvs'])
  def im(key):return o.assets_file.objects[ts[key]['m_Texture']['m_PathID']].read().image.convert('RGBA')
  base=np.asarray(im('_BaseMap'));shade=np.asarray(im('_ShadeMap'));skin=shade[:,:,3]>127;rgb=base[:,:,:3][skin];tone=np.median(rgb,axis=0) if len(rgb) else np.median(base[:,:,:3].reshape(-1,3),axis=0);name=char+'.png';im('_RampMap').save(root/name);rows.append({'bundle':str(p),'materialPathID':o.path_id,'tone':tone.tolist(),'ramp':name});seen.add(char)
(root/'ramps.json').write_text(json.dumps(rows,indent=2));print(len(rows),'character ramps')
