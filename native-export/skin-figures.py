# Task W: crop actual pixels and measure fixed, manually selected skin patches (CIELAB D65).
from pathlib import Path
import json,csv
import numpy as np
from PIL import Image,ImageDraw
W=Path('/work/motion-bake/task-W');V=Path('/work/motion-bake/task-V');O=W/'figures';O.mkdir(exist_ok=True)
VARIANTS=('off','all','rgb-only','a-only','neutral-a','source','mask-source-off','mask-source-all','sat-source-off','sat-source-all','ramp2','ramp3')
ROIS={
 'ichika':{'face':[(483,244),(494,242),(491,253),(485,255)],'arm':[(511,281),(518,280),(518,310),(510,334),(508,332)],'legs':[(511,432),(520,432),(522,467),(511,467)],'torso':[(480,282),(499,283),(498,324),(480,324)],'hair':[(502,249),(508,254),(505,269),(500,259)]},
 'miku':{'face':[(484,248),(494,245),(491,257),(484,261)],'arm':[(507,271),(510,271),(510,279),(507,279)],'legs':[(502,391),(516,392),(517,410),(505,410)],'torso':[(481,293),(496,294),(495,325),(481,325)],'hair':[(502,238),(510,243),(506,251),(501,246)]}}
ROIS['ichika']['eye-band']=[(484,234),(497,234),(497,242),(484,242)]
ROIS['miku']['eye-band']=[(484,238),(498,238),(498,248),(484,248)]
SOURCE_ROIS={'miku':{'face':[(659,209),(676,209),(668,222),(660,219)],'arm':[(699,251),(706,253),(709,268),(702,271)],'legs':[(649,448),(675,450),(668,467),(646,461)]},'ichika':{'face':[(650,194),(675,194),(670,211),(655,214)],'arm':[(715,288),(729,290),(731,310),(717,307)],'legs':[(627,472),(652,474),(640,510),(622,510)]}}
CROPS={'face':(450,216,529,270),'arm':(499,260,539,366),'legs':(445,375,541,477)}
def lab(rgb):
 x=np.asarray(rgb,dtype=float)/255;x=np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
 xyz=x@np.array([[.4124564,.2126729,.0193339],[.3575761,.7151522,.1191920],[.1804375,.0721750,.9503041]])/np.array([.95047,1,1.08883]);f=np.where(xyz>(6/29)**3,np.cbrt(xyz),xyz/(3*(6/29)**2)+4/29)
 return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),-1)
def mask(im,polygon):
 m=Image.new('L',im.size);ImageDraw.Draw(m).polygon(polygon,fill=255);return np.array(m)>0
def picture(actor,variant):return W/'captures'/actor/variant/'ttmr001-28.000.png'
def panel(paths,labels,name,crops=None):
 rows=list(crops.items()) if crops else [(None,None)];width=280 if crops else 480;height=250 if crops else 270
 canvas=Image.new('RGB',(width*len(paths),len(rows)*(height+28)),'#202020');d=ImageDraw.Draw(canvas)
 for row,(region,crop) in enumerate(rows):
  for col,(path,label) in enumerate(zip(paths,labels)):
   im=Image.open(path).convert('RGB');im=im.crop(crop) if crop else im
   im.thumbnail((width,height),Image.Resampling.NEAREST) if not crops else None
   if crops:
    scale=min(width/im.width,height/im.height);im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.NEAREST)
   x=col*width;y=row*(height+28);canvas.paste(im,(x+(width-im.width)//2,y+28));d.text((x+5,y+7),label+(' / '+region if region else ''),fill='white')
 canvas.save(O/name)
rows=[];source_records={};source_stats={}
for p in sorted((W/'source-captures').glob('*/capture.json')):
 j=json.loads(p.read_text())
 if j.get('success') and j.get('actor'):source_records[j['actor']]=p.parent/'scene-ext-motion-28s.png'
for actor in ROIS:
 offpath=picture(actor,'off');allpath=picture(actor,'all')
 if not offpath.exists() or not allpath.exists():continue
 off=Image.open(offpath).convert('RGB');allim=Image.open(allpath).convert('RGB');offlab=lab(np.array(off));alllab=lab(np.array(allim))
 overlay=off.copy();d=ImageDraw.Draw(overlay)
 for name,poly in ROIS[actor].items():d.line(poly+[poly[0]],fill='red',width=1);d.text(poly[0],name,fill='yellow')
 overlay.resize((1920,1080)).save(O/(actor+'-rois.png'))
 refs={}
 if actor in source_records and actor in SOURCE_ROIS:
  im=Image.open(source_records[actor]).convert('RGB');a=lab(np.array(im));overlay=im.copy();d=ImageDraw.Draw(overlay)
  for region,poly in SOURCE_ROIS[actor].items():
   m=mask(im,poly);v=a[m];refs[region]=(v.mean(0),v[v[:,0]<=np.quantile(v[:,0],.25)].mean(0));d.line(poly+[poly[0]],fill='red',width=2);d.text(poly[0],region,fill='red')
  overlay.save(O/(actor+'-source-rois.png'));source_stats[actor]={k:{'Lab':v[0].tolist(),'shadowLab':v[1].tolist()} for k,v in refs.items()}
 for variant in VARIANTS:
  p=picture(actor,variant)
  if not p.exists():continue
  im=Image.open(p).convert('RGB');a=lab(np.array(im))
  for region,poly in ROIS[actor].items():
   m=mask(off,poly);dark=m&(offlab[:,:,0]<=np.quantile(offlab[m][:,0],.25));mean=a[m].mean(0);shadow=a[dark].mean(0)
   ref,refdark=refs.get(region,(np.full(3,np.nan),np.full(3,np.nan)))
   rows.append({'actor':actor,'variant':variant,'region':region,'pixels':int(m.sum()),'shadowPixels':int(dark.sum()),'L':mean[0],'a':mean[1],'b':mean[2],'shadowL':shadow[0],'shadowA':shadow[1],'shadowB':shadow[2],'deltaE_off':np.linalg.norm(mean-offlab[m].mean(0)),'deltaE_all':np.linalg.norm(mean-alllab[m].mean(0)),'shadowDeltaE_off':np.linalg.norm(shadow-offlab[dark].mean(0)),'shadowDeltaE_all':np.linalg.norm(shadow-alllab[dark].mean(0)),'meanPixelDeltaE_off':np.linalg.norm(a[m]-offlab[m],axis=1).mean(),'deltaE_source_scene':np.linalg.norm(mean-ref),'shadowDeltaE_source_scene':np.linalg.norm(shadow-refdark)})
  if variant not in ('off','all'):panel([offpath,p,allpath],['skin OFF',variant,'all ON'],actor+'-'+variant+'-close.png',CROPS)
 if picture(actor,'source').exists():
  paths=[offpath,allpath,picture(actor,'source'),V/'captures/native/ttmr001-28.000.png'];labels=['skin OFF','all ON (JSna)','source tint + native A','native Temari']
  panel(paths,labels,actor+'-recommendation.png');panel(paths,labels,actor+'-recommendation-close.png',CROPS)
  if actor in source_records:panel([source_records[actor],picture(actor,'source')],['Prsk-3D source (different scene)','native mechanism / source tint'],actor+'-source-reference.png')
if rows:
 with (W/'metrics.csv').open('w') as f:writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
(W/'source-region-lab.json').write_text(json.dumps(source_stats,indent=2))
(W/'roi-definitions.json').write_text(json.dumps({'native':ROIS,'source':SOURCE_ROIS,'darkSideDefinition':'Lowest baseline L quartile, fixed coordinates; screen-space proxy, not measured ramp U.','sourceSceneCaveat':'Different scene, pose, camera and lighting; absolute source-scene deltaE is descriptive, not an isolated shader error.'},indent=2))
print('measurements',len(rows),'source captures',list(source_records))
# Native/source ramp strips and sampled alpha curves, with measured channel differences.
catalogue=json.loads((W/'survey/ramps.json').read_text());native=next(x for x in catalogue if 'jsna' in x['ramp']);ref=np.array(Image.open(W/'survey'/native['ramp']).convert('RGBA'));analysis=[];strips=[]
for actor in ('ichika','miku'):
 for variant in ('off','all','ramp2','ramp3','source'):
  report=W/'output'/actor/variant/'report.json'
  if not report.exists():continue
  j=json.loads(report.read_text());choice=j['rampChoice'];a=np.array(Image.open(W/'survey'/choice['ramp']).convert('RGBA'))
  if variant=='off':a=np.tile(np.array([229,204,220,255],dtype='uint8'),(1,256,1))
  if variant=='source':
   import runpy
   skin=runpy.run_path(str(Path(__file__).with_name('skin-ramp.py')));a=np.array(skin['faithful'](Image.fromarray(a),j['sourceShadow']['linearShadowBaseRatio']))
  sampled=np.array(Image.fromarray(a).resize((ref.shape[1],ref.shape[0]),Image.Resampling.NEAREST))
  analysis.append({'actor':actor,'variant':variant,'choice':choice,'shape':list(a.shape),'firstRGBA':a[0,0].tolist(),'lastRGBA':a[0,-1].tolist(),'alphaMinMax':[int(a[:,:,3].min()),int(a[:,:,3].max())],'alphaMeanAbsDeltaJSna':float(abs(sampled[:,:,3].astype(float)-ref[:,:,3]).mean()),'rgbMeanAbsDeltaJSna':float(abs(sampled[:,:,:3].astype(float)-ref[:,:,:3]).mean())});strips.append((actor+' '+variant+' '+choice['ramp'],a))
canvas=Image.new('RGB',(850,90*len(strips)),'#202020');d=ImageDraw.Draw(canvas)
for i,(label,a) in enumerate(strips):
 y=i*90;d.text((5,y+2),label,fill='white');canvas.paste(Image.fromarray(a[:,:,:3]).resize((600,35)),(5,y+23));curve=a[0,:,3];d.line([(610+k*230/(len(curve)-1),y+58-float(v)*35/255) for k,v in enumerate(curve)],fill='white',width=1);d.text((615,y+65),'A vs U (0 to 1)',fill='white')
canvas.save(O/'ramps-and-alpha.png');(W/'ramp-analysis.json').write_text(json.dumps(analysis,indent=2))
