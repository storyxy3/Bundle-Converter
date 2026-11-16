# Derive native chain presets from serialized references and measured rest transforms.
import json, pathlib, math, collections
root=pathlib.Path(__file__).parent
rigs=json.loads((root/'native-rigs.json').read_text()); raw=json.loads((root/'serialized-rigs.json').read_text()); by={r['bundle']:r for r in rigs}; presets=[]
def category(n):
 n=n.lower()
 if 'skirt' in n:return 'skirt'
 if 'hair' in n:
  if 'front' in n:return 'front-hair'
  if 'side' in n:return 'side-hair'
  return 'back-hair'
 return 'accessory'
for r in raw:
 bones={b['name']:b for b in by[r['bundle']]['bones']}
 components={c['name']:c for c in r['components'] if c['type']=='ActorSwingDynamicBone'}
 for c in r['components']:
  if c['type']!='ActorSwingChain':continue
  layers=c['data']['chains']['layers']
  for i,ref in enumerate(c['data']['rootBones']):
   chain=[l['bones'][i]['name'] for l in layers if i<len(l['bones'])]
   if not chain or any(n not in bones for n in chain):continue
   points=[bones[n]['position'] for n in chain]; spacing=[math.dist(a,b) for a,b in zip(points,points[1:])]
   presets.append({'category':category(chain[0]),'bundle':r['bundle'],'root':chain[0],'names':chain,'length':sum(spacing),'spacing':spacing,'settings':[bones[n]['settings'] for n in chain],'layers':[{k:v for k,v in l.items() if k!='bones'} for l in layers],'surfaceWidth':len(c['data']['rootBones'])})
(root/'presets.json').write_text(json.dumps(presets,indent=2))
print('presets',len(presets),collections.Counter(p['category'] for p in presets))
