from pathlib import Path
from PIL import Image
import base64, io, json, re

root = Path(__file__).resolve().parent.parent
assets = root / 'assets5'
rigs = json.loads((assets / 'rigs_v11.json').read_text(encoding='utf-8'))
embedded = {}
for name, rig in rigs.items():
    if name == 'duck':
        embedded[name] = dict(rig, urls={'mallard_icon':'data:image/png;base64,' + base64.b64encode((assets/'mallard_icon.png').read_bytes()).decode('ascii')})
        continue
    keys = ['head_open', 'head_closed', 'ear_l', 'ear_r'] + [p[0] for p in rig['layers']] + [p[0] for p in rig.get('headExtras', [])]
    urls = {}
    for key in dict.fromkeys(keys):
        src = assets / (f'{name}_{key}_round9.png' if name=='yuno' and key in ['arm8_l','arm8_r'] else f'{name}_{key}_round10.png' if name in ['ritsu','nonoka'] and key in ['arm8_l','arm8_r'] else f'miyako_{key}_round12.png' if name=='miyako' and key in ['head_open','head_closed'] else f'maru_{key}_round14.png' if name=='maru' else f'{name}_{key}.png')
        if not src.exists():
            continue
        cached = src.with_suffix('.webp')
        if cached.exists() and ((name in ['ritsu','nonoka'] and key in ['arm_l','arm_r']) or cached.stat().st_mtime_ns >= src.stat().st_mtime_ns):
            payload = cached.read_bytes()
        else:
            im = Image.open(src).convert('RGBA')
            if name != 'maru': im.thumbnail((600, 600), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            im.save(stream, format='WEBP', quality=100 if name=='maru' else 91, lossless=name=='maru', method=4, exact=True)
            payload = stream.getvalue()
            cached.write_bytes(payload)
        urls[key] = 'data:image/webp;base64,' + base64.b64encode(payload).decode('ascii')
    embedded[name] = dict(rig, urls=urls)

css = '''
/* Generated raster cutouts: every character pixel comes from image generation. */
.raster-rig{position:relative;width:240px;height:280px;overflow:visible;pointer-events:none;animation:rig-breathe 6s ease-in-out infinite;animation-delay:var(--phase,0s);transform-origin:50% 230px}
.raster-rig img{position:absolute;display:block;max-width:none;pointer-events:none;user-select:none;-webkit-user-drag:none}
.rig-head{position:absolute;animation:rig-tilt 11s ease-in-out infinite;animation-delay:var(--phase,0s);transform-origin:50% 88%;overflow:visible}
.rig-head img{inset:0;width:100%;height:100%}.rig-closed{opacity:0;animation:rig-close 7.6s linear infinite;animation-delay:var(--phase,0s)}.rig-open{opacity:1;animation:rig-open 7.6s linear infinite;animation-delay:var(--phase,0s)}
.rig-ear-l{transform-origin:28% 45%;animation:rig-ear 9s ease-in-out infinite}.rig-ear-r{transform-origin:72% 45%;animation:rig-ear 9s ease-in-out -3s infinite reverse}
.rig-tail{transform-origin:15% 75%;animation:rig-tail 8s ease-in-out infinite}.rig-arm_l,.rig-arm_r{transform-origin:50% 12%;animation:rig-arm 6s ease-in-out infinite}.rig-arm_r{animation-delay:-2s}
@keyframes rig-breathe{50%{transform:translateY(-1.2px) scale(1.009,1.013)}}@keyframes rig-tilt{30%{transform:rotate(-1.1deg)}70%{transform:rotate(1.3deg)}}
@keyframes rig-ear{0%,38%,58%,100%{transform:rotate(0)}45%{transform:rotate(-3deg)}51%{transform:rotate(1deg)}}@keyframes rig-tail{50%{transform:rotate(3deg)}}@keyframes rig-arm{50%{transform:rotate(2deg)}}
@keyframes rig-open{0%,44.4%,46.4%,100%{opacity:1}44.5%,46.3%{opacity:0}}@keyframes rig-close{0%,44.4%,46.4%,100%{opacity:0}44.5%,46.3%{opacity:1}}
@media(prefers-reduced-motion:reduce){.raster-rig,.raster-rig *{animation:none!important}.rig-open{opacity:1}.rig-closed{opacity:0}}
'''
js = 'const RASTER_RIGS=' + json.dumps(embedded, ensure_ascii=True, separators=(',', ':')) + ';\n' + '''
function rasterPuppet(name,handsOnly=false){
 const rig=RASTER_RIGS[name]; if(!rig)return '';
 const tag=(key,x,y,w,h,cls='')=>rig.urls[key]?'<img alt="" draggable="false" class="rig-'+key+' '+cls+'" src="'+rig.urls[key]+'" style="left:'+x+'px;top:'+y+'px;width:'+w+'px;height:'+h+'px">':'';
 let behind='',front='';
 for(const [key,x,y,w,h] of rig.layers){let im=tag(key,x,y,w,h,key==='tail'?'rig-tail':name==='yuno'&&key==='body'?'rig-body':'');if(rig.shoulders&&rig.shoulders[key])im=im.replace('style="','style="--shoulder:'+rig.shoulders[key][0]+'px '+rig.shoulders[key][1]+'px;');if(key==='tail'||key==='body'||key.startsWith('foot_'))behind+=im;else if(!handsOnly&&name==='yuno'&&key.startsWith('arm')){}else front+=im;}
 const [x,y,w,h]=rig.head;
 const earBoxes=rig.ears||[[0,0,w,h],[0,0,w,h]];
 let ears='';earBoxes.forEach((b,i)=>{let markup=tag(i?'ear_r':'ear_l',...b,i?'rig-ear-r':'rig-ear-l');if(rig.earOrigins)markup=markup.replace('style="','style="transform-origin:'+rig.earOrigins[i]+';');ears+=markup;});
 const earsFront=rig.earsFront===undefined?name==='arale':rig.earsFront;
 const face=tag('head_open',0,0,w,h,'rig-open')+tag('head_closed',0,0,w,h,'rig-closed');
 const extras=(rig.headExtras||[]).map(p=>tag(...p)).join('');
 const head='<div class="rig-head" style="left:'+x+'px;top:'+y+'px;width:'+w+'px;height:'+h+'px">'+(earsFront?face+ears:ears+face)+extras+'</div>';
 const contents=handsOnly?rig.layers.filter(p=>p[0].startsWith('arm')).map(p=>{let im=tag(...p);const joint=rig.shoulders&&rig.shoulders[p[0]];return joint?im.replace('style="','style="--shoulder:'+joint[0]+'px '+joint[1]+'px;'):im}).join('')+head:(name==='maru'?behind+head+front:behind+front+(name==='yuno'?'':head));
 const phase=({arale:0,yuno:-.7,ritsu:-1.3,miyako:-.4,nonoka:-1.7,duck:-2.4,maru:-3.1})[name];
 return '<foreignObject class="raster-character" data-character="'+name+(handsOnly?'-hands':'')+'" x="-120" y="-'+rig.baseline+'" width="240" height="280" overflow="visible"><div xmlns="http://www.w3.org/1999/xhtml" class="raster-rig rig-'+name+'" style="--phase:'+phase+'s;transform-origin:50% '+rig.baseline+'px" aria-hidden="true">'+contents+'</div></foreignObject>';
}
function fox(){return rasterPuppet('arale')}
function ferret(){return rasterPuppet('yuno')}
function bear(){return rasterPuppet('ritsu')}
function maltese(){return rasterPuppet('miyako')}
function rabbit(){return rasterPuppet('nonoka')}
function duck(){return rasterPuppet('duck')}
function maru(){return rasterPuppet('maru')}
'''
html = (root / 'birthday_bg_v2.html').read_text(encoding='utf-8')
a = html.index('// BEGIN CHARACTER ARTWORK')
b = html.index('// END CHARACTER ARTWORK') + len('// END CHARACTER ARTWORK')
html = html[:a] + '// BEGIN GENERATED RASTER PUPPETS\n' + js + '// END GENERATED RASTER PUPPETS' + html[b:]
html = html.replace('</style>', css + '\n</style>', 1)
# A duplicate foreground SVG paw existed only to fix the old vector DJ's occlusion.
html = re.sub(r' layer\(\.68,`.*?`\)\+\n', '', html)
ya=html.index('function yunoScene(){');yb=html.index('function ritsuScene(){',ya)
ys=html[ya:yb].replace(' layer(1,`', " layer(.68,placed(675,585,1.55,rasterPuppet('yuno',true)))+\n layer(1,`",1)
html=html[:ya]+ys+html[yb:]
html = html.replace('placed(652,598,1.65,maltese())', 'placed(652,598,1.35,maltese())')
html = html.replace('placed(436,592,1.28,duck())', 'placed(436,592,.8,duck())')
html = html.replace('placed(877,592,1.2,maru())', 'placed(877,592,.85,maru())')
html = html.replace('BACKGROUND STUDY · 02', 'ILLUSTRATED WORLDS · 03')
html = html.replace('</style>', (assets/'round7.css').read_text(encoding='utf-8')+'\n</style>',1)
html = html.replace('// Lifecycle:', (assets/'round7.js').read_text(encoding='utf-8')+'\n// Lifecycle:',1)
html = html.replace('</main>', '<p style="font-size:10px;opacity:.6;text-align:center">비공식 팬 제작 · AI 생성 일러스트 · 공식과 무관</p></main>')
html = html.replace('preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false"', 'preserveAspectRatio="xMidYMid slice" role="group" aria-label="Birthday character scene"')
html = html.replace('</style>', (assets/'round8.css').read_text(encoding='utf-8')+'\n</style>',1)
html = html.replace('</style>', (assets/'round11.css').read_text(encoding='utf-8')+'\n</style>',1)
html = html.replace('</style>', (assets/'round12.css').read_text(encoding='utf-8')+'\n</style>',1)
html = html.replace(" const rig=RASTER_RIGS[name]; if(!rig)return '';", " const rig=RASTER_RIGS[name]; if(!rig)return '';\n"+(assets/'mallard_renderer13.js').read_text(encoding='utf-8'))
html = html.replace('placed(436,592,.8,duck())','placed(398,562,1,duck())')
html = html.replace('contact(436,596,48,8,','contact(392,566,78,9,')
html = html.replace('</style>', (assets/'round13.css').read_text(encoding='utf-8')+'\n</style>',1)
html = html.replace('placed(877,592,.85,maru())','placed(904,592,.85,maru())')
html = html.replace('contact(877,599,47,8,','contact(904,594,54,8,')
html = html.replace('</style>', (assets/'round14.css').read_text(encoding='utf-8')+'\n</style>',1)
# Round 15: scoped DJ timing and deck controls; every raster rig stays v11-identical.
a=html.index('function yunoScene(){');b=html.index('function ritsuScene(){',a)
ys=html[a:b]
assert ys.count('<g class="spin">')==2
ys=ys.replace('<g class="spin">','<g class="spin dj-record15" data-dj-record="left">',1)
ys=ys.replace('<g class="spin">','<g class="spin dj-record15" data-dj-record="right">',1)
right_marker="${path('M0 -44L4 -27','none',`stroke=\"${C.cyan}\" stroke-width=\"1\"`)}"
assert ys.count('${circle(0,0,11,C.cyan)}</g>')==1
ys=ys.replace('${circle(0,0,11,C.cyan)}</g>','${circle(0,0,11,C.cyan)}'+right_marker+'</g>',1)

ma=ys.index('${[-22,-9,4,17].map');mb=ys.index('${[-137,-123,122,136]',ma)
ys=ys[:ma]+(assets/'dj_mixer15.svg').read_text(encoding='utf-8')+ys[mb:]
html=html[:a]+ys+html[b:]
html=html.replace('// Lifecycle:',(assets/'round19.js').read_text(encoding='utf-8')+'\n// Lifecycle:',1)
needle="floorLines=[...svg.querySelectorAll('.floor-line')];"
assert html.count(needle)==1
html=html.replace(needle,needle+'setupYuno15();')
a=html.index(' if(current===1){eq.forEach(');b=html.index('floorLines.forEach',a)
html=html[:a]+' if(current===1){renderYuno15(time);'+html[b:]
html=html.replace('</style>',(assets/'round15.css').read_text(encoding='utf-8')+'\n</style>',1)
encoded = html.encode('utf-8')
assert len(encoded) <= 12 * 1024 * 1024, len(encoded)
(root / 'birthday_bg_v16.html').write_bytes(encoded)
print(f'Built v16: {len(encoded):,} bytes; {len(embedded)} generated puppets')
