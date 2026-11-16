# Task W: controlled offline asset variants, retaining V geometry, shader contracts and camera.
import runpy,pathlib,json,shutil,subprocess,hashlib,os
import numpy as np
from PIL import Image
M=runpy.run_path(str(pathlib.Path(__file__).with_name('material-native.py')))
W=pathlib.Path('/work/motion-bake/task-W');V=pathlib.Path('/work/motion-bake/task-V');U=M['U']
VARIANTS=('off','all','rgb-only','a-only','neutral-a','source','mask-source-off','mask-source-all','sat-source-off','sat-source-all','ramp2','ramp3')
def watchdog():
 if pathlib.Path('/work/gakumas/work/codex/HANDOFF_NOW').exists():raise SystemExit(75)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def generate(actor,label):
 watchdog();out=W/'output'/actor/label;out.mkdir(parents=True,exist_ok=True);records=[]
 ratio,shadow=M['character_shadow'](actor);tone,choice=M['character_skin'](actor)
 catalogue=json.loads((V/'survey/ramps.json').read_text());ranked=sorted(catalogue,key=lambda r:np.linalg.norm(np.array(r['tone'])-tone))
 ramp=Image.open(V/'survey'/choice['ramp']).convert('RGBA')
 if label in ('ramp2','ramp3'):choice=ranked[int(label[-1])-1];ramp=Image.open(V/'survey'/choice['ramp']).convert('RGBA')
 for p in sorted((V/'output'/actor/'no-skin').glob('*.unity3d')):
  e=M['load'](p);original=M['load'](U/('actor-out' if actor=='ichika' else 'miku/actor-out')/p.name)
  orig_mats=[o for o in original.objects if o.type.name=='Material']
  for o in list(e.objects):
   if o.type.name!='Material':continue
   d=o.read_typetree();owner=o.assets_file;typ=dict(d['m_SavedProperties']['m_Floats']).get('_ShaderType')
   oldref=owner.objects.get(M['texref'](d,'_RampMap'))
   try:oldim=M['pixels'](oldref) if oldref else Image.new('RGBA',ramp.size,'white')
   except IsADirectoryError:
    # U's two Ichika eye ramps have dimensions but no payload. Neutral white is the explicit split-control fallback.
    oldim=Image.new('RGBA',ramp.size,'white');records.append({'material':d['m_Name'],'missingOriginalRampPayload':'split controls use neutral white RGBA; off preserves the original bundle'})
   old=np.array(oldim.resize(ramp.size,Image.Resampling.NEAREST))
   result=np.array(ramp)
   if label=='rgb-only':result[:,:,3]=old[:,:,3]
   if label=='a-only':result[:,:,:3]=old[:,:,:3]
   if label=='neutral-a':result[:,:,:3]=255
   if label=='source':result=np.array(M['SKIN']['faithful'](ramp,ratio))
   if label in ('off','mask-source-off','sat-source-off'):result=None
   if result is not None:M['setref'](d,'_RampMap',M['import_texture'](owner,Image.fromarray(result),'W_'+d['m_Name']+'_RampMap',4 if label=='source' else None))
   sp=owner.objects.get(M['texref'](d,'_ShadeMap'));s=np.array(M['pixels'](sp) if sp else Image.new('RGBA',(1,1),(0,0,0,0)));before=float((s[:,:,3]>127).mean())
   if label.startswith('mask-source') and sp and typ in (0,1,8,9):
    # U source-converted ShadeMap alpha, before V's native-face transfer / body colour inference.
    om=next((x for x in orig_mats if x.read_typetree()['m_Name']==d['m_Name']),orig_mats[0]);od=om.read_typetree()
    try:src=M['pixels'](om.assets_file.objects[M['texref'](od,'_ShadeMap')])
    except IsADirectoryError:
     sm=json.loads((U/'miku/source.json').read_text())['parts'][0 if '_body.' in p.name else 1]['materials'][0];tx=sm['textures'];src=Image.open(U/'miku'/tx['_ShadowTex']['file']).convert('RGBA');b=np.array(Image.open(U/'miku'/tx['_MainTex']['file']).convert('RGBA'));value=np.array(Image.open(U/'miku'/tx['_ValueTex']['file']).resize((b.shape[1],b.shape[0])));mask=value[:,:,0]>127;mask|=(b[:,:,0]>b[:,:,1]*1.02)&(b[:,:,1]>b[:,:,2]*1.01)&(b[:,:,0]>170)&(b[:,:,2]>120);a=np.array(src);a[:,:,3]=mask*255;src=Image.fromarray(a)
    s[:,:,3]=np.array(src.resize((s.shape[1],s.shape[0])))[:,:,3]
    M['setref'](d,'_ShadeMap',M['import_texture'](owner,Image.fromarray(s),'W_'+d['m_Name']+'_ShadeMap'))
   records.append({'bundle':p.name,'material':d['m_Name'],'type':typ,'skinCoverageBefore':before,'skinCoverageAfter':float((s[:,:,3]>127).mean())})
   o.save_typetree(d)
  (out/p.name).write_bytes(e.file.save(packer='lz4'))
 if label.startswith('sat-source'):
  p=U/'content-native/tln_live_ttmr-001.unity3d';e=M['load'](p);changed=[]
  for o in e.objects:
   if o.type.name!='MonoBehaviour':continue
   try:d=o.read_typetree()
   except Exception:continue
   if 'skinSaturation' in d and d['skinSaturation']['m_OverrideState']:
    changed.append([o.path_id,d['skinSaturation']['m_Value']]);d['skinSaturation']['m_Value']=0.;o.save_typetree(d)
  (out/p.name).write_bytes(e.file.save(packer='lz4'));records.append({'sourceMatchedSaturation':1.,'changedNativeVolumeOverrides':changed})
 (out/'report.json').write_text(json.dumps({'actor':actor,'variant':label,'rampChoice':choice,'sourceShadow':shadow,'records':records},indent=2))
 print('GENERATED',actor,label,flush=True)
def capture(actor,label):
 watchdog();out=W/'captures'/actor/label;out.mkdir(parents=True,exist_ok=True)
 bundles=sorted((W/'output'/actor/label).glob('*.unity3d'));signature={p.name:digest(p) for p in bundles}
 if (out/'signature.json').exists() and json.loads((out/'signature.json').read_text())==signature and (out/'ttmr001-28.000.png').exists() and 'LIVE_QUIT' in (out/'player.log').read_text(errors='replace'):return
 content=W/'content'/(actor+'-'+label)
 subprocess.run(['/work/gakumas/tools/venv/bin/python','/work/motion-bake/task-S/converter/stage-native.py',str(U/'content-native'),str(content),*[arg for p in bundles for arg in ('--bundle',str(p))]],check=True)
 # Reuse V's exact player command; only generated input/output roots differ.
 shell=(U/'material-capture.sh').read_text();shell=shell[shell.index('ulimit -n'):].replace('"$content"',str(content)).replace('"$out"',str(out)).replace('"$out/player.log"',str(out/'player.log')).replace('"$out/console.log"',str(out/'console.log'))
 r=subprocess.run(['bash','-c',shell]);watchdog()
 if r.returncode or not (out/'player.log').exists() or 'LIVE_QUIT' not in (out/'player.log').read_text(errors='replace'):raise RuntimeError(f'Capture failed {actor}/{label}: {r.returncode}')
 (out/'signature.json').write_text(json.dumps(signature,indent=2));print('CAPTURED',actor,label,flush=True)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--actor',choices=['ichika','miku']);p.add_argument('--variant',choices=VARIANTS);p.add_argument('--generate-only',action='store_true');a=p.parse_args()
 for actor in ([a.actor] if a.actor else ('ichika','miku')):
  for label in ([a.variant] if a.variant else VARIANTS):
   generate(actor,label)
   if not a.generate_only:capture(actor,label)
