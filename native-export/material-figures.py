# Compose captured pixels only; crop and enlarge face/hair for inspection.
from pathlib import Path
from PIL import Image,ImageDraw
root=Path('/work/motion-bake/task-V');captures=root/'captures';out=root/'figures';out.mkdir(exist_ok=True)
def panel(paths,labels,name,crop=None):
 ims=[]
 for p in paths:
  im=Image.open(p).convert('RGB')
  if crop:im=im.crop(crop).resize((540,480),Image.Resampling.NEAREST)
  ims.append(im)
 canvas=Image.new('RGB',(sum(im.width for im in ims),max(im.height for im in ims)+30),'#202020');draw=ImageDraw.Draw(canvas);x=0
 for im,label in zip(ims,labels):canvas.paste(im,(x,30));draw.text((x+8,8),label,fill='white');x+=im.width
 canvas.save(out/name)
for actor in ('ichika','miku'):
 off=captures/actor/'off/ttmr001-28.000.png';all_on=captures/actor/'all/ttmr001-28.000.png'
 if not off.exists():continue
 for switch in ('hair','face','classes','skin','outline','eyes','mapping','all'):
  on=all_on;comparison_off=off if switch=='all' else captures/actor/('no-'+switch)/'ttmr001-28.000.png'
  if not on.exists() or not comparison_off.exists():continue
  paths=[comparison_off,on];labels=[actor+' '+('U baseline' if switch=='all' else switch+' OFF (others ON)'),actor+' all ON']
  panel(paths,labels,f'{actor}-{switch}.png');panel(paths,labels,f'{actor}-{switch}-close.png',(400,165,580,325))
 if all_on.exists():panel([captures/'native/ttmr001-28.000.png',off,all_on],['Native Temari',actor+' U baseline',actor+' all'],f'{actor}-native.png')
# Compact overview; the individual 3x crops remain available at full size.
names=('hair','face','classes','skin','outline','eyes','mapping')
contact=Image.new('RGB',(2160,510*len(names)),'#202020')
for row,name in enumerate(names):
 for col,actor in enumerate(('ichika','miku')):
  p=out/f'{actor}-{name}-close.png'
  if p.exists():contact.paste(Image.open(p),(col*1080,row*510))
contact.resize((1080,1785)).save(out/'switch-contact-sheet.png')
