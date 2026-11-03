from playwright.sync_api import sync_playwright
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page()
 print(page.evaluate('''()=>{
 const a=document.createElement('canvas'),b=document.createElement('canvas');a.width=b.width=30;a.height=b.height=200;
 const ca=a.getContext('2d'),cb=b.getContext('2d'),g=cb.createLinearGradient(0,0,0,1);g.addColorStop(0,'red');g.addColorStop(1,'blue');
 for(let i=0;i<3;i++){const y=5+i*40,h=25+i*10,gg=ca.createLinearGradient(0,y,0,y+h);gg.addColorStop(0,'red');gg.addColorStop(1,'blue');ca.fillStyle=gg;ca.fillRect(i*10,y,10,h);
 cb.save();cb.translate(i*10,y);cb.scale(1,h);cb.fillStyle=g;cb.fillRect(0,0,10,1);cb.restore()}
 const x=ca.getImageData(0,0,30,200).data,y=cb.getImageData(0,0,30,200).data;return {max:Math.max(...x.map((v,i)=>Math.abs(v-y[i]))),a:[...x.slice(20*30*4,20*30*4+4)],b:[...y.slice(20*30*4,20*30*4+4)]};
 }'''))
 b.close()
