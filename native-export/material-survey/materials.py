# Offline census: statistics describe sampled texels, not artist-labelled ground truth.
import collections,json,pathlib,warnings
import UnityPy,numpy as np
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1'
warnings.simplefilter('ignore')
root=pathlib.Path(__file__).parent
records=[]; hist={}; failures=[]
# Costume face materials reference textures in the base-face CAB; load those local dependencies together.
face_pool=UnityPy.Environment();cab_sources={}
for face_path in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*_face.unity3d')):
 face_pool.load_file(str(face_path))
 for cab in face_pool.cabs:
  if cab not in cab_sources:cab_sources[cab]=str(face_path)
for p in sorted(pathlib.Path('/work/gakumas/models/bundles').glob('mdl_chr_*')):
 if not p.stem.endswith(('_body','_hair','_face')):continue
 try:
  e=UnityPy.load(str(p));objs={o.path_id:o for o in e.objects};cache={}
  def tex(ref):
   k=(ref['m_FileID'],ref['m_PathID'])
   if not k[1]:return None
   if k not in cache:
    owner=o.assets_file if not k[0] else face_pool.cabs.get(o.assets_file.externals[k[0]-1].path.rsplit('/',1)[-1].lower())
    if owner is None:raise ValueError('Unresolved local texture dependency '+o.assets_file.externals[k[0]-1].path)
    cache[k]=np.asarray(owner.objects[k[1]].read().image.convert('RGBA'))
   return cache[k]
  for o in e.objects:
   if o.type.name!='Material':continue
   d=o.read_typetree();sp=d['m_SavedProperties'];f=dict(sp['m_Floats']);typ=int(f.get('_ShaderType',-1));ts=dict(sp['m_TexEnvs']);images={k:tex(v['m_Texture']) for k,v in ts.items()}
   rec={'bundle':str(p),'pathID':o.path_id,'name':d['m_Name'],'type':typ,'keywords':d.get('m_ValidKeywords',[]),'floats':f,'colors':dict(sp['m_Colors']),'textures':{k:{'pathID':v['m_Texture']['m_PathID'],'fileID':v['m_Texture']['m_FileID'],'archive':o.assets_file.externals[v['m_Texture']['m_FileID']-1].path if v['m_Texture']['m_FileID'] else None,'shape':list(images[k].shape) if images[k] is not None else None} for k,v in ts.items()}}
   de=images.get('_DefMap');base=images.get('_BaseMap');shade=images.get('_ShadeMap')
   if de is not None:
    # Equal bounded grid per material prevents 2048 maps dominating smaller maps.
    de=de[::max(1,de.shape[0]//128),::max(1,de.shape[1]//128)]
    labels=np.full(de.shape[:2],'cloth',dtype='<U12')
    if typ==8:labels[:]='hair'
    elif typ==9:labels[:]='face'
    elif typ in (3,4,5,6,7):labels[:]='eyes'
    else:
     labels[de[:,:,2]>127]='metal';labels[(de[:,:,1]>160)&(de[:,:,2]<=127)]='leather'
     if shade is not None:
      from PIL import Image
      a=np.asarray(Image.fromarray(shade).resize((de.shape[1],de.shape[0])))[:,:,3];labels[a>127]='skin'
    rec['regions']={}
    for label in np.unique(labels):
     pixels=de[labels==label];rec['regions'][str(label)]={'samples':len(pixels),'median':np.median(pixels,axis=0).tolist()}
     key=f'{typ}/{label}';h=hist.setdefault(key,np.zeros((4,256),dtype=np.int64))
     for c in range(4):h[c]+=np.bincount(pixels[:,c],minlength=256)
   records.append(rec)
 except Exception as ex:failures.append({'bundle':str(p),'error':str(ex)})
 if len(records)%100==0:print(p.name,len(records),flush=True)
summary={}
for key,h in hist.items():
 q=[]
 for row in h:
  cum=row.cumsum();q.append([int(np.searchsorted(cum,cum[-1]*v)) for v in (.1,.5,.9)])
 summary[key]={'samples':int(h[0].sum()),'rgba_p10_p50_p90':q,'histogram':h.tolist()}
(root/'materials.json').write_text(json.dumps({'materials':records,'failures':failures},indent=2))
(root/'presets.json').write_text(json.dumps({'classification':'skin ShadeMap.A>127; metal Def.B>127; leather G>160 and B<=127; remaining cloth. Hair/face/eyes from ShaderType. Proxy classes, not authored semantic labels.','regions':summary},indent=2))
print('DONE',len(records),'failures',len(failures),flush=True)
