from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests,hashlib,json
R=Path(__file__).resolve().parents[2];base='https://mewtype-schduler.vercel.app/'
files=['js/config.js','monitor.html','js/monitorbirthday.js','js/monitorbirthdaylogic.js','js/bdayaudio.js','js/bdayscene-yuno.js','js/bdayplayer.js','css/bdayplayer.css']
def verify(name):
 response=requests.get(base+name,params={'release_check':'6969df5'},timeout=30);response.raise_for_status()
 actual=response.content.decode('utf8').replace('\r\n','\n');expected=(R/'src/frontend'/name).read_text(encoding='utf8')
 assert actual==expected,f'운영 파일 불일치: {name}'
 return {'path':name,'status':response.status_code,'sha256':hashlib.sha256(actual.encode()).hexdigest()}
with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(verify,files))
media=[]
for key in ['noctural','midnight']:
 name=f'assets/birthday/bgm/{key}.mp3';response=requests.get(base+name,headers={'Range':'bytes=0-1023'},stream=True,timeout=30)
 try:
  assert response.status_code==206,(name,response.status_code)
  prefix=next(response.iter_content(1024));source=R/'src/frontend'/name
  with source.open('rb') as f:assert prefix==f.read(1024)
  assert response.headers.get('Content-Range')==f'bytes 0-1023/{source.stat().st_size}'
  media.append({'path':name,'status':response.status_code,'range':response.headers['Content-Range']})
 finally:response.close()
data={'url':base,'version':'v4.11.0','files':results,'media':media}
Path(__file__).with_name('release-probe.json').write_text(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
print(json.dumps(data,indent=2,ensure_ascii=False))
