"""Build aligned blink frames from image-generated art, extracting only generated eye patches."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFilter
from scipy.ndimage import label,find_objects
import numpy as np,json

p=Path(__file__).resolve().parent
closed=Image.open(p/'miyako_round12_closed_generated.png').convert('RGBA')
opened=Image.open(p/'miyako_round12_open_generated.png').convert('RGBA')
if opened.size!=closed.size:opened=opened.resize(closed.size,Image.Resampling.LANCZOS)
# Final centers/patches are checked visually against both generated images before use.
boxes=[(365,520,565,645),(715,540,930,675)]
mask=Image.new('L',closed.size);bounds=Image.new('L',closed.size)
for x0,y0,x1,y1 in boxes:
 ImageDraw.Draw(mask).rounded_rectangle((x0+10,y0+10,x1-10,y1-10),radius=15,fill=255)
 ImageDraw.Draw(bounds).rectangle((x0,y0,x1,y1),fill=255)
mask=mask.filter(ImageFilter.GaussianBlur(5))
mask=Image.fromarray(np.minimum(np.array(mask),np.array(bounds)))
for core in [(385,545,545,633),(740,565,915,666)]:ImageDraw.Draw(mask).rectangle(core,fill=255)
open_frame=Image.composite(opened,closed,mask)
# Keep the exact shared outline/alpha. Mouth, pin, ears, paws, body and keyboard
# are copied from the closed master rather than allowed to drift between frames.
open_frame.putalpha(closed.getchannel('A'))
alpha=np.array(closed.getchannel('A'));labels,count=label(alpha>128)
sizes=np.bincount(labels.ravel());sizes[0]=0;main=int(sizes.argmax())
ys,xs=np.where(labels==main)
box=(max(0,int(xs.min())-3),max(0,int(ys.min())-3),min(closed.width,int(xs.max())+4),min(closed.height,int(ys.max())+4))
closed.crop(box).save(p/'miyako_head_closed_round12.png')
open_frame.crop(box).save(p/'miyako_head_open_round12.png')
r=json.loads((p/'rigs_v8.json').read_text())
w=230;h=round(w*(box[3]-box[1])/(box[2]-box[0]))
r['miyako']={'revision':12,'head':[(240-w)/2,243-h,w,h],'ears':[],'layers':[],'baseline':243}
(p/'rigs_v9.json').write_text(json.dumps(r,indent=2))
a=np.array(closed);b=np.array(open_frame);difference=np.any(a!=b,axis=2)
mouth=(slice(635,708),slice(570,708))
proof={'sharedCrop':box,'rigHead':r['miyako']['head'],'eyePatchBoxes':boxes,'sameAlpha':bool(np.array_equal(a[:,:,3],b[:,:,3])),'mouthUnchanged':bool(np.array_equal(a[mouth],b[mouth])),'outsideEyePatchesUnchanged':bool(not np.any(difference&(np.array(mask)==0))),'changedPixels':int(difference.sum())}
assert proof['sameAlpha'] and proof['mouthUnchanged'] and proof['outsideEyePatchesUnchanged'] and proof['changedPixels']>0
(p/'round12_frame_alignment.json').write_text(json.dumps(proof,indent=2))
print(json.dumps(proof,indent=2))
