from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
p=D/'scripts/verify_birthday_gapless.py';s=p.read_text(encoding='utf8')
s=s.replace('data:inputs[0][0]', 'data:inputs[0].map(channel=>channel.slice())')
s=s.replace('let count=0,bad=0,sum=0,max=0;', 'let count=0,bad=0,sum=0,max=0;const channels=new Set();')
s=s.replace('for(const chunk of chunks)for(let k=0;k<chunk.data.length;k++){', 'for(const chunk of chunks)for(let ch=0;ch<chunk.data.length;ch++)for(let k=0;k<chunk.data[ch].length;k++){\n    channels.add(ch);')
s=s.replace('getChannelData(0),n=frame-', 'getChannelData(ch),n=frame-')
s=s.replace('chunk.data[k]-data[n]', 'chunk.data[ch][k]-data[n]')
s=s.replace('return {index:audio.index,count,bad,', 'return {index:audio.index,channels:[...channels],count,bad,')
s=s.replace("  assert row['count']>5000,row", "  assert row['channels']==[0,1],row\n  assert row['count']>10000,row")
p.write_text(s,encoding='utf8',newline='\n')
p=D/'scripts/verify_birthday_addendum.py';s=p.read_text(encoding='utf8')
s=s.replace("  results[str(w)]=rows", """  results[str(w)]=rows
  if w==1440:
   # 실제 최종 픽셀의 유노 조명이 부모 brightness에 다시 잘려 회색이 되지 않아야 한다.
   rgb=Image.open(OUT/'addendum-1440-7.5.png').convert('RGB').getpixel((720,400))
   results['spotlight_color']=rgb
   assert rgb[0]>150 and max(rgb)-min(rgb)>40,rgb""")
p.write_text(s,encoding='utf8',newline='\n')
p=D/'docs/BIRTHDAY_MUSIC_SCENE_VERIFICATION.md';s=p.read_text(encoding='utf8').replace('경계 앞뒤 80ms씩의 출력 샘플을', '경계 앞뒤 80ms씩의 스테레오 출력 샘플을')
s=s.replace('- 모바일 390', '- PC 유노 조명의 실제 최종 픽셀도 검사해 중간 클리핑으로 회색이 되지 않는지 확인했다.\n- 모바일 390')
p.write_text(s,encoding='utf8',newline='\n')
m=json.loads((B/'manifest.json').read_text(encoding='utf8'))
for n in m:m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
