from pathlib import Path
import json,re
p=Path(__file__).resolve().parent;root=p.parent
def data(version):return json.loads(re.search(r'const RASTER_RIGS=(.*?);\n',(root/f'birthday_bg_v{version}.html').read_text(encoding='utf-8'))[1])
before=data(7);after=data(8);proof=json.loads((p/'round11_original_hashes.json').read_text());report={}
def without_arms(rig):
 rig=json.loads(json.dumps(rig));rig.pop('shoulders',None)
 rig['layers']=[v for v in rig['layers'] if not v[0].startswith('arm')]
 if 'urls' in rig:rig['urls']={k:v for k,v in rig['urls'].items() if not k.startswith('arm')}
 return rig
for name in ['ritsu','nonoka']:
 same=without_arms(before[name])==without_arms(after[name])
 meta=json.loads(json.dumps(after[name]));meta.pop('urls')
 source=without_arms(meta)==without_arms(proof['originalRigs'][name])
 report[name]={'nonArmArtworkAndGeometryUnchanged':same,'originalRigBaseRestored':source,'oldReplacementArmsAbsent':not any(k.startswith('arm8') for k in after[name]['urls'])}
 assert same and source and report[name]['oldReplacementArmsAbsent']
(p/'round11_scope_check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
