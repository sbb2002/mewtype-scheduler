from pathlib import Path
BASE=Path(__file__).parent/'delivery'
p=BASE/'src/frontend/js/bdaymusic.selfcheck.mjs';s=p.read_text(encoding='utf8');s=s.replace('>=introBrightness(t)', '>=introBrightness(t)-1e-12').replace('<=introBrightness(t)', '<=introBrightness(t)+1e-12');p.write_text(s,encoding='utf8',newline='\n')
p=BASE/'src/frontend/js/bdayaudio.js';s=p.read_text(encoding='utf8')
s=s.replace('const r={i,start,offset,end:start+node.buffer.duration-offset,node};queue.push(r);', '''const fs=context.sampleRate,startFrame=Math.round(start*fs),offsetFrame=Math.round(offset*fs);
    start=startFrame/fs;offset=offsetFrame/fs;
    const r={i,start,offset,end:(startFrame+node.buffer.length-offsetFrame)/fs,node};queue.push(r);''')
s=s.replace('function startBuffers(offset,when=context.currentTime)', 'function startBuffers(offset,when=context.currentTime+.08)')
p.write_text(s,encoding='utf8',newline='\n')
for name,marker in [('docs/BIRTHDAY_SKIN.md','\n### 음악 장면 3차 인계'),('CLAUDE.md','\n생일 음악 후속 구현은')]:
 p=BASE/name;s=p.read_text(encoding='utf8');first=s.find(marker);second=s.find(marker,first+len(marker))
 if second>=0:s=s[:second]
 p.write_text(s.rstrip()+'\n',encoding='utf8',newline='\n')
p=BASE/'scripts/verify_birthday_gapless.py';s=p.read_text(encoding='utf8')
s=s.replace("page.wait_for_timeout(900)", """if turn==2:
   page.wait_for_timeout(200)
   page.evaluate('()=>{const until=performance.now()+1000;while(performance.now()<until){}}')
  else:page.wait_for_timeout(900)""")
s=s.replace('const r=scheduled.find(r=>t>=r.start&&t<r.end);', 'const r=scheduled.find(r=>frame>=Math.round(r.start*fs)&&frame<Math.round(r.end*fs));')
s=s.replace('n=Math.round((t-r.start+r.offset)*fs)', 'n=frame-Math.round(r.start*fs)+Math.round(r.offset*fs)')
p.write_text(s,encoding='utf8',newline='\n')
