# Provenance manifest for generated bundles and actual player captures.
import hashlib,json,pathlib,re
root=pathlib.Path('/work/motion-bake/task-W')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
outputs=[];captures=[]
for p in sorted((root/'output').glob('*/*/mdl*.unity3d')):
 outputs.append({'file':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size})
for p in sorted((root/'captures').glob('**/player.log')):
 text=p.read_text(errors='replace');times=re.findall(r'LIVE_CAPTURE requested=([^ ]+) actual=([^ ]+)',text);images=[{'file':str(q.relative_to(root)),'sha256':sha(q)} for q in sorted(p.parent.glob('*.png'))]
 captures.append({'log':str(p.relative_to(root)),'quit':'LIVE_QUIT' in text,'times':times,'images':images,'exceptions':len(re.findall(r'\b\w*Exception\b',text))})
sources={str(p):sha(p) for p in pathlib.Path('/work/motion-bake/task-U').iterdir() if p.is_file() and (p.name.startswith('material') or p.name.startswith('skin'))}
player=pathlib.Path('/work/gakumas/live-urp-native/Build/Linux/TrueEnd.x86_64')
(root/'artifact-manifest.json').write_text(json.dumps({'player':{'file':str(player),'sha256':sha(player)},'sources':sources,'outputs':outputs,'captures':captures,'sourceReferences':[{'file':str(p.relative_to(root)),'sha256':sha(p)} for p in (root/'source-captures').glob('*/*28s.png')]},indent=2))
print('bundle files',len(outputs),'capture logs',len(captures),'screenshots',sum(len(c['images']) for c in captures),'quit',sum(c['quit'] for c in captures),'exceptions',sum(c['exceptions'] for c in captures))
# Manifest/staged/output hashes, including unchanged native motions and camera-containing timeline data.
staged=[]
for directory in sorted((root/'content').iterdir()):
 manifest=directory/'manifest.json'
 if not manifest.exists():continue
 actor,variant=directory.name.split('-',1);entries=json.loads(manifest.read_text())['bundles']
 for entry in entries:
  p=directory/entry['file'];expected=entry.get('sha256');actual=sha(p);output=root/'output'/actor/variant/(entry['name']+'.unity3d');source=output if output.exists() else pathlib.Path('/work/motion-bake/task-U/content-native')/entry['file']
  staged.append({'capture':directory.name,'name':entry['name'],'manifestMatches':actual==expected,'sourceMatches':actual==sha(source)})
(root/'staging-inspection.json').write_text(json.dumps(staged,indent=2))
print('staged',len(staged),'mismatches',sum(not x['manifestMatches'] or not x['sourceMatches'] for x in staged))
