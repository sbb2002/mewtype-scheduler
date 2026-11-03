from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js')
s=p.read_text(encoding='utf8')
s=s.replace('h=Math.ceil(groundBottom)-395','h=Math.ceil(groundBottom)')
s=s.replace("[gc,mc,w].forEach(x=>{x.setTransform(1,0,0,1,0,0);x.globalCompositeOperation='source-over';x.clearRect(0,0,1200,grid.height);x.translate(0,-395)});", "[gc,mc,w].forEach(x=>{x.globalCompositeOperation='source-over';x.clearRect(0,0,1200,groundBottom)});")
s=s.replace('w.drawImage(mask,0,395)','w.drawImage(mask,0,0)').replace('c.drawImage(grid,0,395);c.drawImage(bands,0,395);','c.drawImage(grid,0,0);c.drawImage(bands,0,0);')
s=s.replace("gc=grid.getContext('2d')","gc=grid.getContext('2d',{willReadFrequently:true})").replace("mc=mask.getContext('2d')","mc=mask.getContext('2d',{willReadFrequently:true})").replace("w=bands.getContext('2d')","w=bands.getContext('2d',{willReadFrequently:true})")
p.write_text(s,encoding='utf8',newline='\n')
