from pathlib import Path
import json, os
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
out=Path(os.environ['TEMP'])/'birthday-greeting-motion';out.mkdir(exist_ok=True)
css='\n'.join((root/'src/frontend/css'/name).read_text(encoding='utf8') for name in ['birthday.css','bdayplayer.css'])
results={}
with sync_playwright() as p:
 browser=p.chromium.launch()
 for width,height in [(1440,900),(390,844),(320,740)]:
  page=browser.new_page(viewport={'width':width,'height':height})
  page.set_content('<html data-bday-full data-bday-revealed><style>body{background:radial-gradient(ellipse at bottom,#b72874,#170725);height:100vh;margin:0}'+css+'</style><div id="bday-greet"><span class="bday-greet__en">Happy Birthday.</span><span class="bday-greet__who">유노 · 11.01</span></div></html>')
  page.evaluate('''()=>{for(const a of document.getAnimations())a.pause()}''')
  def sample(t):
   return page.evaluate('''t=>{for(const a of document.getAnimations())a.currentTime=t;const q=s=>+getComputedStyle(document.querySelector(s)).opacity;return {group:q('#bday-greet'),en:q('.bday-greet__en'),who:q('.bday-greet__who')}}''',t)
  early=sample(200);assert 0<early['en']<1 and early['who']==0,early
  settled=sample(1800);assert settled=={'group':1,'en':1,'who':1},settled
  page.screenshot(path=str(out/f'{width}-greeting-glow.png'))
  start=sample(4800);middle=sample(6200);end=sample(7600)
  assert start['group']==1 and .4<middle['group']<.6 and end['group']==0,(start,middle,end)
  page.emulate_media(reduced_motion='reduce');assert page.locator('.bday-greet__en').evaluate('e=>getComputedStyle(e).animationName')=='none'
  results[str(width)]={'stagger':early,'settled':settled,'fade_midpoint':middle,'fade_end':end,'reduced_motion':True}
  page.close()
 browser.close()
(out/'motion.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n',encoding='utf8')
print('Greeting stagger, glow, 2.8s fade and reduced-motion: PASS (desktop + mobile)')
