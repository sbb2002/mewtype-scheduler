from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
old="""   lc.setTransform(1,0,0,1,0,0);lc.clearRect(0,0,w,h);lc.filter=`brightness(${introBrightness(t)/.3})`;lc.drawImage(canvas,0,0);lc.filter='none';
   const x=ox+effect.x*s,y=oy+effect.y*s,max=Math.max(...[[0,0],[w,0],[0,h],[w,h]].map(([a,b])=>Math.hypot(a-x,b-y))),radius=effect.wave*(max+80);"""
new="""   const x=ox+effect.x*s,y=oy+effect.y*s,max=Math.max(...[[0,0],[w,0],[0,h],[w,h]].map(([a,b])=>Math.hypot(a-x,b-y))),radius=effect.wave*(max+80);
   // マスク外の画素には明るさフィルタを計算しない。
   const left=Math.max(0,Math.floor(x-radius)),top=Math.max(0,Math.floor(y-radius)),right=Math.min(w,Math.ceil(x+radius)),bottom=Math.min(h,Math.ceil(y+radius));
   lc.setTransform(1,0,0,1,0,0);lc.clearRect(0,0,w,h);lc.filter=`brightness(${introBrightness(t)/.3})`;
   if(right>left&&bottom>top)lc.drawImage(canvas,left,top,right-left,bottom-top,left,top,right-left,bottom-top);lc.filter='none';"""
new=new.replace('// マスク外の画素には明るさフィルタを計算しない。','// 파면 마스크 밖의 픽셀에는 밝기 필터를 계산하지 않는다.')
assert old in s;s=s.replace(old,new)
p.write_text(s,encoding='utf8',newline='\n')
