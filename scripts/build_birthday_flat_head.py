"""저장소 머리의 눈만 수평으로 바꾼다. 외부 자산·이미지 생성은 사용하지 않는다."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
def build():
 source=Image.open(ROOT/'src/frontend/assets/birthday/yuno/head_closed.webp').convert('RGBA')
 a=np.array(source);height,width=a.shape[:2];mask=np.zeros((height,width),np.uint8)
 for x0,y0,x1,y1 in [(63,211,152,252),(229,211,321,250)]:
  rgb=a[y0:y1,x0:x1,:3];mask[y0:y1,x0:x1]=((rgb[:,:,0]<220)&(rgb[:,:,1]<130))*255
 mask=np.array(Image.fromarray(mask).filter(ImageFilter.MaxFilter(5)))>0
 # 눈에 가려지지 않은 양쪽 앞머리 경계로 숨은 경계의 연속 곡선을 추정한다.
 samples=[]
 for x in range(208,271):
  for y in range(195,259):
   if mask[y-2:y+3,x-2:x+3].any():continue
   if a[y,x,1]<=140<a[y+1,x,1] and min(a[y,x,0],a[y+1,x,0])>235:
    samples.append((x,y+(140-float(a[y,x,1]))/(float(a[y+1,x,1])-float(a[y,x,1]))));break
 boundary=np.polyfit(*np.array(samples).T,3)
 yy,xx=np.indices((height,width));f=np.stack([np.ones((height,width)),xx/width,yy/height,(xx/width)**2,xx*yy/(width*height),(yy/height)**2],axis=-1)
 clean=~np.array(Image.fromarray(mask.astype('uint8')*255).filter(ImageFilter.MaxFilter(7))).astype(bool)
 regions=[(xx>60)&(xx<155)&(yy>200)&(yy<255)&(a[:,:,0]>230)&(a[:,:,1]>140),
          (xx>200)&(xx<330)&(yy>190)&(yy<243)&(a[:,:,0]>230)&(a[:,:,1]<110),
          (xx>200)&(xx<280)&(yy>195)&(yy<263)&(a[:,:,0]>230)&(a[:,:,1]>155)]
 fields=[]
 for region in regions:
  valid=region&clean;model=np.linalg.lstsq(f[valid],a[valid,:3].astype(float),rcond=None)[0];fields.append(f@model)
 weight=1/(1+np.exp(np.clip(-(yy-np.polyval(boundary,xx))/.58,-60,60)))
 fill=fields[1]*(1-weight[:,:,None])+fields[2]*weight[:,:,None]
 fill=np.where((xx<190)[:,:,None],fields[0],fill)
 rgb=a[:,:,:3].astype(float);rgb[mask]=fill[mask]
 # 같은 재질끼리만 경계 색을 이어 주어 피부·머리카락이 서로 번지지 않는다.
 labels=np.where(xx<190,1,np.where(weight<.05,2,np.where(weight>.95,1,0)))
 update=mask&(labels>0)
 for _ in range(300):
  total=np.zeros_like(rgb);count=np.zeros((height,width))
  for axis,shift in [(0,-1),(0,1),(1,-1),(1,1)]:
   same=np.roll(labels,shift,axis)==labels;total+=np.roll(rgb,shift,axis)*same[:,:,None];count+=same
  rgb[update]=total[update]/count[update,None]
 out=a.copy();out[mask,:3]=np.rint(np.clip(rgb[mask],0,255)).astype('uint8')
 # 기존 자주색 잉크와 동일한 두께의 둥근 수평 눈꺼풀.
 scale=4;eyes=Image.new('L',(width*scale,height*scale));draw=ImageDraw.Draw(eyes)
 for left,right in [(78,138),(243,303)]:
  y=232;radius=6
  draw.rectangle((left*scale,(y-radius)*scale,right*scale,(y+radius)*scale),fill=255)
  for x in [left,right]:draw.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=255)
 eyes=eyes.resize(source.size,Image.Resampling.LANCZOS)
 core=mask&(a[:,:,0]<120)&(a[:,:,1]<45)
 ink=tuple(np.median(a[core,:3],axis=0).astype('uint8'))+(255,)
 final=Image.composite(Image.new('RGBA',source.size,ink),Image.fromarray(out),eyes)
 final.putalpha(source.getchannel('A'))
 allowed=mask|(np.array(eyes)>0)
 return source,final,allowed

if __name__=='__main__':
 source,final,allowed=build();target=ROOT/'src/frontend/assets/birthday/yuno/head_flat.webp'
 final.save(target,lossless=True,exact=True,method=6)
 saved=np.array(Image.open(target).convert('RGBA'));original=np.array(source)
 assert np.array_equal(saved[~allowed],original[~allowed])
 assert np.array_equal(saved[:,:,3],original[:,:,3])
 print('눈 마스크 외 RGBA 및 전체 알파 동일:',source.size)
