# Offline native material authoring; runtime/player files are never changed.
import copy,json,pathlib,struct,warnings,os,runpy
SKIN=runpy.run_path(str(pathlib.Path(__file__).with_name("skin-ramp.py")))
import UnityPy,numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from scipy.ndimage import maximum_filter,minimum_filter
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.streams import EndianBinaryReader
def refresh(o):
 if o.data is not None:o.reader=EndianBinaryReader(o.data,endian=o.reader.endian);o.byte_start=0;o.byte_size=len(o.data)
UnityPy.config.FALLBACK_UNITY_VERSION='6000.0.77f1';warnings.simplefilter('ignore')
ROOT=pathlib.Path(os.environ.get('V_ROOT','/work/motion-bake/task-W')); U=pathlib.Path(os.environ.get('V_U_ROOT','/work/motion-bake/task-U'))
SWITCHES=('hair','face','classes','skin','outline','eyes','mapping')
def load(p):return UnityPy.load(str(p))
def mesh(o):
 h=MeshHandler(o.read());h.process();return h
def arr(x):return np.asarray(x,dtype=float)
def normalized(v):return (v-v.min(0))/np.maximum(np.ptp(v,axis=0),1e-8)
def mesh_normalized(h,frame=None):
 v=arr(h.m_Vertices)
 if frame is not None:return (v-frame[0])/np.maximum(frame[1]-frame[0],1e-8)
 active=np.unique([i for sub in h.get_triangles() for tri in sub for i in tri]);return (v-v[active].min(0))/np.maximum(np.ptp(v[active],axis=0),1e-8)
def pixels(o):return o.read().image.convert('RGBA')
def image_at(im,uv):
 a=np.asarray(im);uv=np.asarray(uv);return a[np.clip(((1-uv[:,1])*a.shape[0]).astype(int),0,a.shape[0]-1),np.clip((uv[:,0]*a.shape[1]).astype(int),0,a.shape[1]-1)]
def texref(d,k):return dict(d['m_SavedProperties']['m_TexEnvs']).get(k,{}).get('m_Texture',{}).get('m_PathID',0)
def setref(d,k,pid):
 ts=dict(d['m_SavedProperties']['m_TexEnvs']);ts[k]={'m_Texture':{'m_FileID':0,'m_PathID':pid},'m_Scale':{'x':1.,'y':1.},'m_Offset':{'x':0.,'y':0.}};d['m_SavedProperties']['m_TexEnvs']=list(ts.items())
def import_texture(owner,im,name,texture_format=None):
 template=next(o for o in owner.objects.values() if o.type.name=='Texture2D');o=copy.copy(template);o.path_id=max(owner.objects)+1;o.data=template.get_raw_data();owner.objects[o.path_id]=o
 t=o.read();t.m_Name=name
 if texture_format is not None:t.m_TextureFormat=texture_format
 t.image=im
 # Copy native per-slot sampling semantics; data maps must not inherit an sRGB base-map template.
 for key in ('_BaseMap','_ShadeMap','_DefMap','_RampMap','_RampAddMap','_HighlightMap','_ReflectionSphereMap'):
  if not name.endswith(key):continue
  for no,nd in native.values():
   pid=texref(nd,key)
   if not pid or pid not in no.assets_file.objects:continue
   nt=no.assets_file.objects[pid].read();t.m_ColorSpace=nt.m_ColorSpace;t.m_TextureSettings=copy.deepcopy(nt.m_TextureSettings);break
 t.save();refresh(o);return o.path_id
native={};donors={};donorenv=[]
for part in ('body','hair','face'):
 p=pathlib.Path('/work/gakumas/models/bundles')/('mdl_chr_ttmr-'+('base-0000' if part=='face' else 'cstm-0003')+'_'+part+'.unity3d');e=load(p);donorenv.append(e)
 for o in e.objects:
  if o.type.name=='Material':
   d=o.read_typetree();native[int(dict(d['m_SavedProperties']['m_Floats'])['_ShaderType'])]=(o,d)
  if o.type.name=='Mesh' and (part=='face' or o.read_typetree()['m_Name'] in ('Geo_Hair','Geo_Body')):donors[part]=mesh(o)
def donor_image(typ,key):
 o,d=native[typ];pid=texref(d,key);return pixels(o.assets_file.objects[pid]) if pid else None
# Rasterize interpolated donor samples into the source UV chart. Degenerate UVs remain the evidenced native face default.
def bake(uv,tri,values,size=512):
 result=np.tile(np.array([194,0,0,0],dtype=np.uint8),(size,size,1))
 for ids in tri:
  q=uv[ids]*[size-1,-(size-1)]+[0,size-1];lo=np.maximum(np.floor(q.min(0)).astype(int),0);hi=np.minimum(np.ceil(q.max(0)).astype(int),size-1)
  if np.any(hi<lo):continue
  a=q[1]-q[0];b=q[2]-q[0];det=a[0]*b[1]-a[1]*b[0]
  if abs(det)<1e-8:continue
  yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];dx=xx-q[0,0];dy=yy-q[0,1];w1=(dx*b[1]-dy*b[0])/det;w2=(a[0]*dy-a[1]*dx)/det;w0=1-w1-w2;ok=(w0>=-1e-5)&(w1>=-1e-5)&(w2>=-1e-5)
  v=w0[...,None]*values[ids[0]]+w1[...,None]*values[ids[1]]+w2[...,None]*values[ids[2]];result[yy[ok],xx[ok]]=np.clip(v[ok],0,255).astype('uint8')
 return Image.fromarray(result)
def face_labels(h,frame=None):
 proxy=donors['face'];pv=arr(proxy.m_Vertices);sub=proxy.get_triangles();face_env=donorenv[2];refs=next(o.read_typetree()['sharedMaterials'] for o in face_env.objects if o.type.name=='MonoBehaviour' and 'sharedMaterials' in o.read_typetree())
 types=[int(dict(next(x for x in face_env.objects if x.path_id==ref['m_PathID']).read_typetree()['m_SavedProperties']['m_Floats'])['_ShaderType']) for ref in refs]
 centers=[];labels=[];normalized_proxy=normalized(pv)
 for triangles,typ in zip(sub,types):
  for tri in triangles:centers.append(normalized_proxy[list(tri)].mean(0));labels.append(typ)
 tree=cKDTree(centers)
 tri=np.array([t for sub in h.get_triangles() for t in sub]);nv=mesh_normalized(h,frame);_,ids=tree.query(nv[tri].mean(1));return tri,np.array(labels)[ids]

def split_miku_eyes(e,report,frame=None):
 for renderer in list(e.objects):
  if renderer.type.name!='SkinnedMeshRenderer':continue
  rd=renderer.read_typetree();mo=renderer.assets_file.objects[rd['m_Mesh']['m_PathID']];h=mesh(mo);md=mo.read_typetree();tri,lab=face_labels(h,frame);owner=renderer.assets_file;old=owner.objects[rd['m_Materials'][0]['m_PathID']];source=old.read_typetree();subs=[];indices=[];mats=[]
  for typ in (9,3,4,5,6):
   selected=tri[np.isin(lab,(3,4,5))] if typ==3 else tri[lab==typ]
   if not len(selected):continue
   # TODO(qa-recon): source combined eye atlas may need an iris/white texture split beyond geometric proxy classes.
   d=copy.deepcopy(source);_,nd=native[typ];keep=d['m_SavedProperties']['m_TexEnvs'];d['m_SavedProperties']=copy.deepcopy(nd['m_SavedProperties']);d['m_SavedProperties']['m_TexEnvs']=keep;d['m_Name']='V_MikuEyeType'+str(typ);d['m_ValidKeywords']=[k for k in nd['m_ValidKeywords'] if k not in ('_RAMPADD_ON','_LAYERMAP_ON')];d['m_CustomRenderQueue']=nd['m_CustomRenderQueue'];d['disabledShaderPasses']=nd.get('disabledShaderPasses',[])
   if typ==5:
    im=donor_image(5,'_ReflectionSphereMap')
    if im is not None:setref(d,'_ReflectionSphereMap',import_texture(owner,im,d['m_Name']+'Reflection'))
   mat=copy.copy(old);mat.path_id=max(owner.objects)+1;mat.data=old.get_raw_data();owner.objects[mat.path_id]=mat;mat.save_typetree(d);refresh(mat);mats.append({'m_FileID':0,'m_PathID':mat.path_id})
   sm=copy.deepcopy(md['m_SubMeshes'][0]);sm['firstByte']=len(indices)*4;sm['indexCount']=selected.size;sm['baseVertex']=0;sm['firstVertex']=int(selected.min());sm['vertexCount']=int(selected.max()-selected.min()+1);subs.append(sm);indices.extend(selected.ravel().tolist())
  md['m_SubMeshes']=subs;md['m_IndexFormat']=1;md['m_IndexBuffer']=struct.pack('<'+'I'*len(indices),*indices);mo.save_typetree(md);refresh(mo);rd['m_Materials']=mats;renderer.save_typetree(rd);report.append({'eyeProxyTriangleCounts':{str(t):int((lab==t).sum()) for t in np.unique(lab)}})

def repair_miku_hair(source,report):
 # U split only dynamically weighted triangles. Route connected static cap charts to the native hair part too.
 envs={part:load(next(source.glob('*_'+part+'.unity3d'))) for part in ('face','hair')}
 objs={part:next(o for o in e.objects if o.type.name=='Mesh') for part,e in envs.items()};fh=mesh(objs['face']);hh=mesh(objs['hair'])
 if not np.array_equal(arr(fh.m_Vertices),arr(hh.m_Vertices)):raise ValueError('Miku part vertex correspondence changed')
 tri,lab=face_labels(fh);active=np.unique(tri);envs['face_frame']=(arr(fh.m_Vertices)[active].min(0),arr(fh.m_Vertices)[active].max(0));ht=np.array([t for sub in hh.get_triangles() for t in sub]);v=arr(fh.m_Vertices);uv=arr(fh.m_UV0)[:,:2];sm=json.loads((U/'miku/source.json').read_text())['parts'][1]['materials'][0];tx=sm['textures']['_MainTex'];im=Image.open(U/'miku'/tx['file']).convert('RGBA');scale=[tx['scale']['x'],tx['scale']['y']];offset=[tx['offset']['x'],tx['offset']['y']]
 rgb=image_at(im,uv[tri].mean(1)*scale+offset)[:,:3].astype(float);hc=image_at(im,uv[np.unique(ht)]*scale+offset)[:,:3].astype(float);hair=np.median(hc/np.maximum(hc.sum(1)[:,None],1),axis=0);skin=character_skin('miku')[0];skin/=skin.sum();chroma=rgb/np.maximum(rgb.sum(1)[:,None],1)
 warm=(rgb[:,0]>rgb[:,1]*1.02)&(rgb[:,0]>rgb[:,2]*1.01)&(rgb.min(1)>100);allowed=(lab==9)&~warm
 if not (lab==4).any():
  # TODO(qa-recon): no native eye proxy band is available to protect coloured iris triangles.
  report.append({'staticCapTrianglesMoved':0,'reason':'missing eye proxy band'});return envs
 eye_top=float(np.quantile(v[tri[lab==4]].mean(1)[:,1],.95));boundary=np.isin(tri,np.unique(ht)).any(1);seed=allowed&((v[tri].mean(1)[:,1]>eye_top)|boundary)&(np.linalg.norm(chroma-hair,axis=1)<.75*np.linalg.norm(chroma-skin,axis=1))&(np.ptp(rgb,axis=1)>25)
 adjacency={}
 for i in np.flatnonzero(allowed):
  for vertex in tri[i]:adjacency.setdefault(int(vertex),[]).append(int(i))
 selected=set(map(int,np.flatnonzero(seed)));pending=list(selected)
 while pending:
  for vertex in tri[pending.pop()]:
   for neighbor in adjacency.get(int(vertex),[]):
    if neighbor not in selected:selected.add(neighbor);pending.append(neighbor)
 moved=np.array(sorted(selected),dtype=int);keep=np.ones(len(tri),bool);keep[moved]=False
 for part,indices in (('face',tri[keep]),('hair',np.concatenate((ht,tri[moved])))):
  o=objs[part];d=o.read_typetree()
  if len(d['m_SubMeshes'])!=1:raise ValueError('Expected original single-atlas Miku parts')
  points=v[indices];lo=points.min((0,1));hi=points.max((0,1));bounds={'m_Center':dict(zip('xyz',((lo+hi)/2).tolist())),'m_Extent':dict(zip('xyz',((hi-lo)/2).tolist()))};d['m_LocalAABB']=bounds
  sm=d['m_SubMeshes'][0];sm['localAABB']=copy.deepcopy(bounds);sm.update(firstByte=0,indexCount=int(indices.size),baseVertex=0,firstVertex=int(indices.min()),vertexCount=int(indices.max()-indices.min()+1));d['m_IndexFormat']=1;d['m_IndexBuffer']=struct.pack('<'+'I'*indices.size,*indices.ravel());o.save_typetree(d);refresh(o)
 report.append({'staticCapTrianglesMoved':len(moved),'sourceFaceTriangles':len(tri),'sourceHairTriangles':len(ht),'hairChroma':hair.tolist(),'eyeBandTop':eye_top,'policy':'connected non-skin face charts seeded by source hair colour above native eye proxy band or at existing hair boundaries'})
 return envs

def edit_mesh(o,part,enabled,report,frame=None):
 h=mesh(o);v=arr(h.m_Vertices);uv=arr(h.m_UV0)[:,:2];norm=arr(h.m_Normals);tangent=arr(h.m_Tangents);colors=arr(h.m_Colors);d=o.read_typetree();data=bytearray(d['m_VertexData']['m_DataSize']);streams=h.get_streams(o.read().m_VertexData.m_Channels,len(v))
 def write(channel,values,fmt):
  c=d['m_VertexData']['m_Channels'][channel];s=streams[c['stream']]
  for i,val in enumerate(values):struct.pack_into('<'+fmt,data,s.offset+i*s.stride+c['offset'],*val)
 if ('face' in enabled and part in ('face','hair')) or 'outline' in enabled:
  if part in donors:
   proxy=donors[part];pv=arr(proxy.m_Vertices);dist,ids=cKDTree(normalized(pv)).query(mesh_normalized(h,frame));tn=arr(proxy.m_Tangents)[ids,:3]
   if 'face' in enabled and part in ('face','hair'):write(1,arr(proxy.m_Normals)[ids],'3f')
   report.append({'mesh':d['m_Name'],'proxy':part,'normalizedDistanceP50P90':np.quantile(dist,[.5,.9]).tolist()})
  else:
   # Position-welded average; no topology or skin weights change.
   _,inv=np.unique(np.round(v,5),axis=0,return_inverse=True);tn=np.zeros((inv.max()+1,3));np.add.at(tn,inv,norm);tn=tn[inv]
  tn/=np.maximum(np.linalg.norm(tn,axis=1)[:,None],1e-8);write(2,np.column_stack((tn,np.ones(len(tn)))),'4f')
 if 'outline' in enabled:
  proxy=donors.get(part,donors['face']);_,ids=cKDTree(normalized(arr(proxy.m_Vertices))).query(mesh_normalized(h,frame));pc=arr(proxy.m_Colors)[ids];pc=np.clip(np.round(pc*255),0,255).astype('uint8');write(3,pc,'4B')
 d['m_VertexData']['m_DataSize']=bytes(data);o.save_typetree(d);refresh(o)
 return h

def character_skin(actor):
 if actor=='miku':
  sm=json.loads((U/'miku/source.json').read_text())['parts'][1]['materials'][0];im=Image.open(U/'miku'/sm['textures']['_MainTex']['file']).convert('RGBA');b=np.asarray(im);mask=(b[:,:,0]>b[:,:,1]*1.02)&(b[:,:,0]>b[:,:,2]*1.01)&(b[:,:,:3].min(2)>120)
 else:
  env=load(U/'actor-out/mdl_chr_ttmr-base-0000_face.unity3d');mat=next(o for o in env.objects if o.type.name=='Material' and dict(o.read_typetree()['m_SavedProperties']['m_Floats']).get('_ShaderType')==9);md=mat.read_typetree();b=np.asarray(pixels(mat.assets_file.objects[texref(md,'_BaseMap')]));shade=np.asarray(pixels(mat.assets_file.objects[texref(md,'_ShadeMap')]).resize((b.shape[1],b.shape[0])));mask=shade[:,:,3]>127
 if not mask.any():mask=(b[:,:,0]>b[:,:,1]*1.02)&(b[:,:,0]>b[:,:,2]*1.01)&(b[:,:,:3].min(2)>100)
 if not mask.any():raise ValueError('No source facial skin samples; supply a skin mask rather than selecting by clothing colour')
 tone=np.median(b[:,:,:3][mask],axis=0);catalogue=json.loads((ROOT/'survey/ramps.json').read_text());choice=min(catalogue,key=lambda r:np.linalg.norm(np.array(r['tone'])-tone));return tone,choice

def character_shadow(actor):
 if actor=='miku':
  sm=json.loads((U/'miku/source.json').read_text())['parts'][1]['materials'][0];tx=sm['textures'];base=Image.open(U/'miku'/tx['_MainTex']['file']).convert('RGBA');shade=Image.open(U/'miku'/tx['_ShadowTex']['file']).convert('RGBA').resize(base.size)
  value=np.array(Image.open(U/'miku'/tx['_ValueTex']['file']).resize(base.size));mask=value[:,:,0]>127
  images=[]
  for im,key in ((base,'_DefaultSkinColor'),(shade,'_Shadow1SkinColor')):
   a=np.array(im);a[:,:,:3][mask]=(a[:,:,:1][mask]*[sm['colors'][key][k] for k in 'rgb']).astype('uint8');images.append(Image.fromarray(a))
  base,shade=images
 else:
  e=load(U/'actor-out/mdl_chr_ttmr-base-0000_face.unity3d');o=next(o for o in e.objects if o.type.name=='Material' and dict(o.read_typetree()['m_SavedProperties']['m_Floats']).get('_ShaderType')==9);d=o.read_typetree();base=pixels(o.assets_file.objects[texref(d,'_BaseMap')]);shade=pixels(o.assets_file.objects[texref(d,'_ShadeMap')])
 return SKIN['source_ratio'](base,shade)

def run(actor,label,enabled,skin_mode="source"):
 skin_selection=character_skin(actor) if 'skin' in enabled else None
 shadow_selection=character_shadow(actor) if 'skin' in enabled and skin_mode=='source' else None
 source=U/('actor-out' if actor=='ichika' else 'miku/actor-out');out=ROOT/'output'/actor/label;out.mkdir(parents=True,exist_ok=True);report=[];repaired=repair_miku_hair(source,report) if actor=='miku' and 'mapping' in enabled else {}
 for p in sorted(source.glob('mdl*.unity3d')):
  part='face' if '_face.' in p.name else 'hair' if '_hair.' in p.name else 'body'
  if not enabled:(out/p.name).write_bytes(p.read_bytes());continue
  e=repaired[part] if part in repaired else load(p)
  frame=repaired.get('face_frame') if part=='face' else None
  if actor=='miku' and part=='face' and 'eyes' in enabled:split_miku_eyes(e,report,frame)
  objects=list(e.objects);meshes=[o for o in objects if o.type.name=='Mesh'];mh={o.path_id:edit_mesh(o,part,enabled,report,frame) for o in meshes};primary=next(iter(mh.values()))
  for o in objects:
   if o.type.name!='Material':continue
   d=o.read_typetree();f=dict(d['m_SavedProperties']['m_Floats']);typ=int(f.get('_ShaderType',0));owner=o.assets_file
   # Miku prepared materials are indexed source submeshes. Infer source texture purpose, then use native contracts.
   if actor=='miku' and 'mapping' in enabled:
    typ=8 if part=='hair' else 0 if part=='body' else typ if d['m_Name'].startswith('V_MikuEyeType') else 9
   apply_contract=('mapping' in enabled and actor=='miku') or ('eyes' in enabled and typ in (3,4,5,6))
   if apply_contract:
    _,nd=native[typ];keep=d['m_SavedProperties']['m_TexEnvs'];d['m_SavedProperties']=copy.deepcopy(nd['m_SavedProperties']);d['m_SavedProperties']['m_TexEnvs']=keep
    d['m_ValidKeywords']=[k for k in nd['m_ValidKeywords'] if k not in ('_RAMPADD_ON','_LAYERMAP_ON')];d['m_CustomRenderQueue']=nd['m_CustomRenderQueue'];d['disabledShaderPasses']=nd.get('disabledShaderPasses',[])
   def get(k):
    pid=texref(d,k)
    if pid not in owner.objects:return None
    try:return pixels(owner.objects[pid])
    except IsADirectoryError:
     if actor!='miku':raise
     sm=json.loads((U/'miku/source.json').read_text())['parts'][0 if part=='body' else 1]['materials'][0]
     sourcekey={'_BaseMap':'_MainTex','_ShadeMap':'_ShadowTex','_DefMap':'_ValueTex'}.get(k)
     if sourcekey:im=Image.open(U/'miku'/sm['textures'][sourcekey]['file']).convert('RGBA')
     else:im=donor_image(8 if part=='hair' else 9 if part=='face' else 0,k)
     report.append({'repairedEmptyUTexture':k,'material':d['m_Name']});put(k,im);return im
   def put(k,im,texture_format=None):
    if im is not None:setref(d,k,import_texture(owner,im,'V_'+d['m_Name']+k,texture_format))
   base=get('_BaseMap');shade=get('_ShadeMap');de=get('_DefMap')
   if 'mapping' in enabled and actor=='miku':
    # Prepared Miku maps retained unrelated body secondary textures: replace those using the actual base texture.
    source_data=json.loads((U/'miku/source.json').read_text());sm=source_data['parts'][0 if part=='body' else 1]['materials'][0];tx=sm['textures'];sourcebase=Image.open(U/'miku'/tx['_MainTex']['file']).convert('RGBA');value=np.asarray(Image.open(U/'miku'/tx['_ValueTex']['file']).convert('RGBA').resize(sourcebase.size));skin=value[:,:,0]>127
    basearr=np.asarray(Image.open(U/'miku'/tx['_MainTex']['file']).convert('RGBA')).copy();shadow=np.asarray(Image.open(U/'miku'/tx['_ShadowTex']['file']).convert('RGBA').resize(sourcebase.size)).copy()
    for target,col in ((basearr,'_DefaultSkinColor'),(shadow,'_Shadow1SkinColor')):
     tint=sm['colors'][col];palette=np.array([tint[k] for k in ('r','g','b')]);target[:,:,:3][skin]=(target[:,:,:1][skin]*palette).astype('uint8')
    skin|=(basearr[:,:,0]>basearr[:,:,1]*1.02)&(basearr[:,:,1]>basearr[:,:,2]*1.01)&(basearr[:,:,0]>170)&(basearr[:,:,2]>120);shadow[:,:,3]=skin.astype('uint8')*255;definition=np.zeros_like(basearr);definition[:,:,0]=np.clip(2*value[:,:,2].astype(float)-127.5,0,255)
    put('_BaseMap',Image.fromarray(basearr));put('_ShadeMap',Image.fromarray(shadow));put('_DefMap',Image.fromarray(definition));base=get('_BaseMap');shade=get('_ShadeMap');de=get('_DefMap')
    for key in ('_BaseMap','_ShadeMap','_DefMap'):
     ts=dict(d['m_SavedProperties']['m_TexEnvs']);ts[key]['m_Scale']=tx['_MainTex']['scale'];ts[key]['m_Offset']=tx['_MainTex']['offset'];d['m_SavedProperties']['m_TexEnvs']=list(ts.items())
   if 'face' in enabled and typ==9:
    proxy=donors['face'];pv=arr(proxy.m_Vertices);v=arr(primary.m_Vertices);_,ids=cKDTree(normalized(pv)).query(mesh_normalized(primary,frame));values=image_at(donor_image(9,'_DefMap'),arr(proxy.m_UV0)[ids,:2]);values[:,3]=0
    tri=np.array([t for sub in primary.get_triangles() for t in sub],dtype=int)
    if tri is None:raise ValueError('mesh triangles unavailable')
    st=dict(d['m_SavedProperties']['m_TexEnvs'])['_BaseMap'];uv=arr(primary.m_UV0)[:,:2]*[st['m_Scale']['x'],st['m_Scale']['y']]+[st['m_Offset']['x'],st['m_Offset']['y']];put('_DefMap',bake(uv,tri,values))
    native_skin=image_at(donor_image(9,'_ShadeMap'),arr(proxy.m_UV0)[ids,:2])[:,3];mask_values=np.repeat(native_skin[:,None],4,axis=1);mask=np.asarray(bake(uv,tri,mask_values))[:,:,0];shadow=np.asarray(shade).copy();shadow[:,:,3]=np.asarray(Image.fromarray(mask).resize(shade.size,Image.Resampling.BILINEAR));put('_ShadeMap',Image.fromarray(shadow));shade=get('_ShadeMap');d['m_ValidKeywords']=[k for k in d['m_ValidKeywords'] if k!='_DEFMAP_OFF']
   if 'classes' in enabled and typ in (0,1,8):
    a=np.asarray(de if de else Image.new('RGBA',base.size)).copy();b=np.asarray(base.resize((a.shape[1],a.shape[0])));s=np.array(shade.resize((a.shape[1],a.shape[0]))) if shade else b.copy()
    region=np.full(a.shape[:2],'hair' if typ==8 else 'cloth',dtype='<U12');gray=b[:,:,:3].mean(2);contrast=maximum_filter(gray,5)-minimum_filter(gray,5);region[(b[:,:,:3].max(2)-b[:,:,:3].min(2)<25)&(gray>75)&(gray<170)&(contrast>90)]='metal';region[b[:,:,:3].mean(2)<45]='leather';region[s[:,:,3]>127]='skin' if typ!=8 else 'hair'
    if typ==8:region[:]='hair'
    else:
     skin_mask=(s[:,:,3]>127)|((b[:,:,0]>b[:,:,1]*1.02)&(b[:,:,0]>b[:,:,2]*1.01)&(b[:,:,:3].min(2)>100));region[skin_mask]='skin';s[:,:,3]=skin_mask.astype('uint8')*255;put('_ShadeMap',Image.fromarray(s));shade=get('_ShadeMap')
    stats=json.loads((ROOT/'survey/presets.json').read_text())['regions']
    for cls in np.unique(region):
     key=f'{typ}/{cls}';preset=stats.get(key,stats.get('0/'+cls));
     if preset:
      for c in (1,2,3):a[:,:,c][region==cls]=preset['rgba_p10_p50_p90'][c][1]
    put('_DefMap',Image.fromarray(a))
    if typ!=8:
     put('_RampAddMap',donor_image(0,'_RampAddMap'));d['m_ValidKeywords']=list(set(d['m_ValidKeywords'])|{'_RAMPADD_ON'})
     proxy=donors['body'];puv=arr(proxy.m_UV0)[:,:2];pd=image_at(donor_image(0,'_DefMap'),puv);ps=image_at(donor_image(0,'_ShadeMap'),puv);pl=np.full(len(puv),'cloth',dtype='<U12');pl[pd[:,2]>127]='metal';pl[(pd[:,1]>160)&(pd[:,2]<=127)]='leather';pl[ps[:,3]>127]='skin';pc=np.rint(arr(proxy.m_Colors)*255).astype(int);rows={cls:int(np.bincount(pc[pl==cls,1]&15,minlength=16).argmax()) for cls in np.unique(pl)}
     mo=meshes[0];md=mo.read_typetree();mc=md['m_VertexData']['m_Channels'][3];stream=primary.get_streams(mo.read().m_VertexData.m_Channels,primary.m_VertexCount)[mc['stream']];buf=bytearray(md['m_VertexData']['m_DataSize']);uv=arr(primary.m_UV0)[:,:2];ix=np.clip((uv[:,0]*region.shape[1]).astype(int),0,region.shape[1]-1);iy=np.clip(((1-uv[:,1])*region.shape[0]).astype(int),0,region.shape[0]-1)
     for i,cls in enumerate(region[iy,ix]):
      offset=stream.offset+i*stream.stride+mc['offset']+1;buf[offset]=(buf[offset]&240)|rows.get(str(cls),0)
     md['m_VertexData']['m_DataSize']=bytes(buf);mo.save_typetree(md);refresh(mo);report.append({'material':d['m_Name'],'classRampAddRows':rows,'donor':'mdl_chr_ttmr-cstm-0003_body/Geo_Body'})
   if 'skin' in enabled:
    # Selected native curve, optionally tinted from the character source ShadowTex.
    tone,choice=skin_selection;ramp=Image.open(ROOT/'survey'/choice['ramp']).convert('RGBA')
    if skin_mode=='source':ramp=SKIN['faithful'](ramp,shadow_selection[0])
    # Native ramps use RGBA32 (4); source hair templates can otherwise recompress their alpha.
    put('_RampMap',ramp,4 if skin_mode=='source' else None);report.append({'material':d['m_Name'],'skinRamp':choice,'sourceTone':tone.tolist(),'skinMode':skin_mode,'sourceShadow':shadow_selection[1] if shadow_selection else None})
   if 'hair' in enabled and typ==8:
    native_hi=donor_image(8,'_HighlightMap');profile=np.asarray(native_hi).mean(axis=1);uv=arr(primary.m_UV0)[:,:2];v=arr(primary.m_Vertices);axis=np.linalg.lstsq(np.column_stack((uv,np.ones(len(uv)))),v[:,1],rcond=None)[0][:2];axis/=max(np.linalg.norm(axis),1e-8);yy,xx=np.mgrid[0:base.height,0:base.width];t=(xx/base.width*axis[0]+(1-yy/base.height)*axis[1]);t=(t-t.min())/max(np.ptp(t),1e-8);hi=profile[np.clip((t*(len(profile)-1)).astype(int),0,len(profile)-1)].copy();b=np.asarray(base).astype(float);st=dict(d['m_SavedProperties']['m_TexEnvs'])['_BaseMap'];active=np.unique([i for sub in primary.get_triangles() for tri in sub for i in tri]);samples=image_at(base,uv[active]*[st['m_Scale']['x'],st['m_Scale']['y']]+[st['m_Offset']['x'],st['m_Offset']['y']]);color=np.median(samples[:,:3],axis=0);hi[:,:,:3]=hi[:,:,:3]/np.maximum(hi[:,:,:3].mean((0,1)),1)*color;put('_HighlightMap',Image.fromarray(np.clip(hi,0,255).astype('uint8')))
    _,nd=native[8];co=dict(d['m_SavedProperties']['m_Colors']);co.update({k:v for k,v in nd['m_SavedProperties']['m_Colors'] if 'Highlight' in k or '_SpecularThreshold'==k});d['m_SavedProperties']['m_Colors']=list(co.items())
   if 'eyes' in enabled and typ in (3,4,6):
    eye_stats=json.loads((ROOT/'survey/presets.json').read_text())['regions'][str(typ)+'/eyes'];rgba=tuple(c[1] for c in eye_stats['rgba_p10_p50_p90']);put('_DefMap',Image.new('RGBA',de.size if de else base.size,rgba));report.append({'material':d['m_Name'],'nativeEyeDefRGBA':list(rgba)})
   if 'eyes' in enabled and typ==5:put('_ReflectionSphereMap',donor_image(5,'_ReflectionSphereMap'))
   o.save_typetree(d)
  (out/p.name).write_bytes(e.file.save(packer='lz4'))
 (out/'report.json').write_text(json.dumps({'enabled':sorted(enabled),'meshes':report},indent=2));print(actor,label,flush=True)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--skin-mode',choices=['source','nearest'],default='source',help='Source ShadowTex tint with native alpha (default), or V nearest native RGBA');p.add_argument('--actor',choices=['ichika','miku'],required=True);p.add_argument('--variant',required=True);p.add_argument('--enable',help='Comma-separated independent switches; overrides the variant preset');a=p.parse_args();enabled=set(a.enable.split(',') if a.enable else SWITCHES if a.variant=='all' else set(SWITCHES)-{a.variant[3:]} if a.variant.startswith('no-') else [] if a.variant=='off' else [a.variant]);unknown=enabled-set(SWITCHES)
 if unknown:p.error('Unknown switches: '+','.join(sorted(unknown)))
 run(a.actor,a.variant,enabled,a.skin_mode)
