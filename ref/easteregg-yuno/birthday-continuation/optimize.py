from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js')
s=p.read_text(encoding='utf8')
s=s.replace("h=Math.ceil(groundBottom)","h=Math.ceil(groundBottom)-395")
s=s.replace("[gc,mc,w].forEach(x=>{x.globalCompositeOperation='source-over';x.clearRect(0,0,1200,groundBottom)});", "[gc,mc,w].forEach(x=>{x.setTransform(1,0,0,1,0,0);x.globalCompositeOperation='source-over';x.clearRect(0,0,1200,grid.height);x.translate(0,-395)});")
s=s.replace("w.drawImage(mask,0,0)","w.drawImage(mask,0,395)")
s=s.replace("c.drawImage(grid,0,0);c.drawImage(bands,0,0);","c.drawImage(grid,0,395);c.drawImage(bands,0,395);")
start=s.index('  if(effect.spot){c.save();const top=')
end=s.index('  if(effect.spot){\n',start)
old=s[start:end]
body=old[old.index('c.save();'):old.rindex(';}')+1]
body=body.replace('c.save();const top=Math.min(-100,-oy/s),g=', 'c.save();const top=spotTop,g=')
body=body.replace('effect.spot*', '')
body=body.replace('c.', 'sc.')
new="""  if(effect.spot){
   // 원뿔과 바닥 조명의 모양은 크기가 바뀔 때만 계산하고 알파로 점등한다.
   const spotTop=Math.min(-100,-oy/s),key=`${w}:${h}:${s}:${oy}`;
   if(spotCacheKey!==key){spotCacheKey=key;spotLayer.width=w;spotLayer.height=h;const sc=spotLayer.getContext('2d');sc.setTransform(s,0,0,s,ox,oy);
BODY
   }
   c.save();c.setTransform(1,0,0,1,0,0);c.globalAlpha=effect.spot;c.drawImage(spotLayer,0,0);c.restore();
  }
""".replace('BODY',body)
s=s[:start]+new+s[end:]
s=s.replace("const lightLayer=document.createElement('canvas'),frontLayer=document.createElement('canvas');", "const lightLayer=document.createElement('canvas'),frontLayer=document.createElement('canvas'),spotLayer=document.createElement('canvas');let spotCacheKey=null;")
s=s.replace("if(frontLayer.width!==w||frontLayer.height!==h){frontLayer.width=w;frontLayer.height=h}","const fw=Math.ceil(440*s),fh=Math.ceil(500*s);if(frontLayer.width!==fw||frontLayer.height!==fh){frontLayer.width=fw;frontLayer.height=fh}")
s=s.replace("fc.clearRect(0,0,w,h);fc.setTransform(s,0,0,s,ox-75*s,oy)","fc.clearRect(0,0,fw,fh);fc.setTransform(s,0,0,s,-455*s,-160*s)")
s=s.replace("c.drawImage(frontLayer,0,0)","c.drawImage(frontLayer,ox+380*s,oy+160*s)")
s=s.replace("canvas.remove();lightLayer.width", "canvas.remove();spotLayer.width=spotLayer.height=0;lightLayer.width")
p.write_text(s,encoding='utf8',newline='\n')
