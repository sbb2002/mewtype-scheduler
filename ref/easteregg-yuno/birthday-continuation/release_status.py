from pathlib import Path
import os,json,requests,sys
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[2]
settings=json.loads((root/'.vercel/project.json').read_text(encoding='utf8'))
token=os.environ.get('VERCEL_TOKEN') or dotenv_values(root/'.env').get('VERCEL_TOKEN')
assert token,'Vercel 인증 정보 없음'
s=requests.Session();s.headers['Authorization']='Bearer '+token
project=s.get('https://api.vercel.com/v9/projects/'+settings['projectId'],params={'teamId':settings['orgId']},timeout=30)
project.raise_for_status();p=project.json()
response=s.get('https://api.vercel.com/v6/deployments',params={'projectId':settings['projectId'],'teamId':settings['orgId'],'target':'production','limit':12},timeout=30)
response.raise_for_status()
deployments=[{'id':d['uid'],'state':d.get('readyState') or d.get('state'),'url':d.get('url'),'sha':d.get('meta',{}).get('githubCommitSha'),'created':d.get('created')} for d in response.json()['deployments']]
data={'project':p.get('name'),'rootDirectory':p.get('rootDirectory'),'framework':p.get('framework'),'deployments':deployments}
out=Path(__file__).with_name('release-status.json');out.write_text(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
print(json.dumps(data,ensure_ascii=False,indent=2))
