# Native highlight spatial structure, with per-bundle/material provenance.
import json,pathlib,warnings
import numpy as np,UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1';warnings.simplefilter('ignore');records=[]
for p in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*_hair.unity3d')):
 e=UnityPy.load(str(p))
 for o in e.objects:
  if o.type.name!='Material':continue
  d=o.read_typetree();sp=d['m_SavedProperties'];ts=dict(sp['m_TexEnvs']);pid=ts.get('_HighlightMap',{}).get('m_Texture',{}).get('m_PathID',0)
  if not pid:continue
  a=np.asarray(o.assets_file.objects[pid].read().image.convert('RGBA'));records.append({'bundle':str(p),'material':d['m_Name'],'pathID':pid,'shape':list(a.shape),'rgbaP10P50P90':np.quantile(a.reshape(-1,4),[.1,.5,.9],axis=0).tolist(),'rowsMeanRGBA':a.mean(axis=1).tolist(),'columnsMeanRGBA':a.mean(axis=0).tolist()})
pathlib.Path(__file__).with_name('highlights.json').write_text(json.dumps(records));print(len(records),'highlight maps')
