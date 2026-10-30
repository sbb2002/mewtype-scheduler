"""Extract generated Maru parts with overlapping hidden roots and aligned blink eyes."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageFilter
import json,numpy as np

p=Path(__file__).resolve().parent
opened=Image.open(p/'maru_round14_open_generated.png').convert('RGBA')
closed_gen=Image.open(p/'maru_round14_closed_generated.png').convert('RGBA')
rgba=np.array(opened);rgba[:,:,3]=np.where(rgba[:,:,3]>=250,255,rgba[:,:,3]);opened=Image.fromarray(rgba)
if closed_gen.size!=opened.size:closed_gen=closed_gen.resize(opened.size,Image.Resampling.LANCZOS)
eye_mask=Image.new('L',opened.size)
for box in [(425,470,550,596),(690,470,820,596)]:ImageDraw.Draw(eye_mask).rounded_rectangle(box,radius=12,fill=255)
eye_mask=eye_mask.filter(ImageFilter.GaussianBlur(4))
for box in [(440,490,540,585),(705,490,808,585)]:ImageDraw.Draw(eye_mask).rectangle(box,fill=255)
guard=np.array(eye_mask);guard[570:638,570:681]=0;eye_mask=Image.fromarray(guard)
closed=Image.composite(closed_gen,opened,eye_mask);closed.putalpha(opened.getchannel('A'))
polygons={
 'head':[(398,215),(458,110),(663,104),(753,200),(844,216),(893,300),(919,400),(947,548),(915,641),(851,691),(750,738),(619,751),(487,735),(401,702),(354,657),(310,588),(296,515),(291,446),(341,365),(358,285)],
 'body':[(420,680),(824,680),(889,797),(941,884),(1010,1080),(943,1190),(257,1190),(219,1040),(287,889),(370,809)],
 'ear_l':[(13,440),(86,405),(141,354),(179,264),(278,205),(376,236),(413,315),(358,392),(315,498),(302,579),(339,667),(380,714),(315,783),(156,797),(34,657),(2,538)],
 'ear_r':[(862,246),(942,204),(1047,228),(1117,313),(1158,392),(1243,416),(1253,566),(1235,678),(1086,790),(939,786),(901,706),(936,637),(948,533),(910,424),(887,343)],
 'arm_l':[(227,599),(327,589),(408,636),(454,706),(485,805),(453,859),(354,857),(275,807),(219,715)],
 'arm_r':[(800,651),(872,608),(964,610),(1017,687),(1015,770),(946,847),(843,865),(767,816),(755,747)],
 'hairpin':[(748,239),(890,239),(890,377),(748,377)]
}
masks={}
for key,points in polygons.items():
 im=Image.new('L',opened.size);ImageDraw.Draw(im).polygon(points,fill=255);masks[key]=np.array(im)
for key in ['head','body']:masks[key]=np.array(Image.fromarray(masks[key]).filter(ImageFilter.MaxFilter(37)))
# The upper chest star belongs entirely to the torso, below the face's chin.
masks['head'][700:,:]=0
pixels=np.array(opened).astype('int16')
gold=(pixels[:,:,0]>140)&(pixels[:,:,1]>85)&(pixels[:,:,2]<190)&(pixels[:,:,0]>pixels[:,:,1])&(pixels[:,:,2]<pixels[:,:,1]+20)
gold_mask=Image.fromarray(gold.astype('uint8')*255).filter(ImageFilter.MaxFilter(5))
masks['hairpin']=np.minimum(masks['hairpin'],np.array(gold_mask))
# Keep the original pixels under the static pin to avoid a transparent pin-shaped
# hole opening between independently resampled head/accessory textures.
# Every original visible pixel is retained. Residual edge tufts are assigned to
# their nearest major region rather than redrawn or deleted.
alpha=np.array(opened.getchannel('A'));union=np.maximum.reduce(list(masks.values()))
yy,xx=np.mgrid[:opened.height,:opened.width];missing=(union==0)&(alpha>0)
for key,where in [('ear_l',(xx<350)&(yy<800)),('ear_r',(xx>930)&(yy<800)),('head',yy<700),('body',np.ones(alpha.shape,dtype=bool))]:
 use=missing&where;masks[key][use]=255;missing[use]=False
master_box=opened.getchannel('A').point(lambda v:255 if v>128 else 0).getbbox()
x0,y0,x1,y1=master_box;scale=230/(x1-x0);bottom=243
boxes={}
for key,m in masks.items():
 mask=Image.fromarray(m)
 states=[('head_open',opened),('head_closed',closed)] if key=='head' else [(key,opened)]
 a=ImageChops.multiply(opened.getchannel('A'),mask)
 box=a.point(lambda v:255 if v>32 else 0).getbbox();boxes[key]=box
 for out_key,frame in states:
  part=frame.copy();part.putalpha(ImageChops.multiply(frame.getchannel('A'),mask));part.crop(box).save(p/f'maru_{out_key}_round14.png')
def rig_box(box):
 a,b,c,d=box;return [round(5+(a-x0)*scale,4),round(bottom-(y1-b)*scale,4),round((c-a)*scale,4),round((d-b)*scale,4)]
head=rig_box(boxes['head'])
def ear_box(key):
 b=rig_box(boxes[key]);return [round(b[0]-head[0],4),round(b[1]-head[1],4),b[2],b[3]]
def origin(key,point):
 box=boxes[key];return [(point[0]-box[0])*scale,(point[1]-box[1])*scale]
ear_origins=[]
for key,point in [('ear_l',(365,320)),('ear_r',(923,325))]:
 v=origin(key,point);ear_origins.append(f'{v[0]:.4f}px {v[1]:.4f}px')
r=json.loads((p/'rigs_v10.json').read_text())
pin=rig_box(boxes['hairpin'])
r['maru']={'revision':14,'head':head,'ears':[ear_box('ear_l'),ear_box('ear_r')],'earsFront':False,'earOrigins':ear_origins,'headExtras':[['hairpin',round(pin[0]-head[0],4),round(pin[1]-head[1],4),pin[2],pin[3]]],'layers':[[key,*rig_box(boxes[key])] for key in ['body','arm_l','arm_r']],'shoulders':{key:origin(key,point) for key,point in [('arm_l',(444,811)),('arm_r',(803,811))]},'baseline':243}
(p/'rigs_v11.json').write_text(json.dumps(r,indent=2))
aa=np.array(opened);bb=np.array(closed)
proof={'masterBox':master_box,'partBoxes':boxes,'rig':r['maru'],'alphaIdentical':bool(np.array_equal(aa[:,:,3],bb[:,:,3])),'mouthIdentical':bool(np.array_equal(aa[570:638,570:681],bb[570:638,570:681])),'outsideEyeRegionsIdentical':bool(np.all(aa[np.array(eye_mask)==0]==bb[np.array(eye_mask)==0])),'allOriginalVisiblePixelsRetained':bool(np.all(np.maximum.reduce(list(masks.values()))[alpha>0]>0))}
assert proof['alphaIdentical'] and proof['mouthIdentical'] and proof['outsideEyeRegionsIdentical'] and proof['allOriginalVisiblePixelsRetained']
(p/'round14_parts.json').write_text(json.dumps(proof,indent=2))
print(json.dumps({k:v for k,v in proof.items() if k!='rig'},indent=2))
