#!/usr/bin/env python3
# Read serialized native authoring directly, preserving PathIDs and resolving bone names.
import json,pathlib,warnings,collections
import UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1'
warnings.simplefilter('ignore')
out=[]
for p in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*')):
 if not (p.name.endswith('_body.unity3d') or p.name.endswith('_hair.unity3d')): continue
 e=UnityPy.load(str(p)); objs={o.path_id:o for o in e.objects}; trees={i:o.read_typetree() for i,o in objs.items() if o.type.name in ('GameObject','Transform','MonoBehaviour','MonoScript')}
 def name(ref):
  d=trees.get(ref.get('m_PathID'),{})
  if 'm_GameObject' in d:d=trees.get(d['m_GameObject']['m_PathID'],{})
  return d.get('m_Name','')
 def resolve(v):
  if isinstance(v,dict):
   if set(v)=={'m_FileID','m_PathID'}:return {'pathID':v['m_PathID'],'fileID':v['m_FileID'],'name':name(v)}
   return {k:resolve(x) for k,x in v.items()}
  if isinstance(v,list):return [resolve(x) for x in v]
  return v
 components=[]
 for i,d in trees.items():
  if objs[i].type.name!='MonoBehaviour':continue
  cls=trees.get(d['m_Script']['m_PathID'],{}).get('m_ClassName','')
  if 'Swing' in cls or 'Quartz' in cls:components.append({'pathID':i,'name':name(d['m_GameObject']),'type':cls,'data':resolve(d)})
 out.append({'bundle':str(p),'components':components})
pathlib.Path(__file__).with_name('serialized-rigs.json').write_text(json.dumps(out,indent=2))
print('serialized prefabs',len(out),'components',sum(len(x['components']) for x in out))
