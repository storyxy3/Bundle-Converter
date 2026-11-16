# Native mesh convention census; bounded vertex sampling, exact source provenance.
import json,pathlib,warnings
import numpy as np,UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1';warnings.simplefilter('ignore');records=[];fail=[]
for p in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*')):
 if not p.stem.endswith(('_body','_hair','_face')):continue
 try:
  for o in UnityPy.load(str(p)).objects:
   if o.type.name!='Mesh':continue
   h=MeshHandler(o.read());h.process();n=np.asarray(h.m_Normals);t=np.asarray(h.m_Tangents);c=np.rint(np.asarray(h.m_Colors)*255).astype(int)
   if len(c)==0:continue
   dots=(n*t[:,:3]).sum(1);rgba=np.stack((c>>4,c&15),axis=-1)
   records.append({'bundle':str(p),'pathID':o.path_id,'name':o.read_typetree()['m_Name'],'vertices':len(n),'normalTangentDotP10P50P90':np.quantile(dots,[.1,.5,.9]).tolist(),'rgbaHiLoP10P50P90':np.quantile(rgba,[.1,.5,.9],axis=0).tolist(),'rgbaHiLoHistograms':[[np.bincount(rgba[:,ch,half],minlength=16).tolist() for half in range(2)] for ch in range(4)]})
 except Exception as ex:fail.append({'bundle':str(p),'error':str(ex)})
pathlib.Path(__file__).with_name('meshes.json').write_text(json.dumps({'meshes':records,'failures':fail},indent=2));print(len(records),'meshes',len(fail),'failures',flush=True)
