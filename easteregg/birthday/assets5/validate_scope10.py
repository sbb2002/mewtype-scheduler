"""Verify unchanged artwork/motion scope and continuous arm/paw alpha silhouettes."""
from pathlib import Path
from PIL import Image
from scipy.ndimage import label
import hashlib,json,numpy as np,re

p=Path(__file__).resolve().parent;root=p.parent
old=(root/'birthday_bg_v6.html').read_text(encoding='utf-8');new=(root/'birthday_bg_v7.html').read_text(encoding='utf-8')
pattern=r'const RASTER_RIGS=(.*?);\n'
before=json.loads(re.search(pattern,old)[1]);after=json.loads(re.search(pattern,new)[1])
report={'characters':{},'oldFilesPreserved':all(hashlib.sha256((root/f).read_bytes()).hexdigest()==h for f,h in json.loads((p/'round10_preserved.json').read_text()).items())}
for n in ['ritsu','nonoka']:
 a=json.loads(json.dumps(before[n]));b=json.loads(json.dumps(after[n]));counts={}
 for rig in [a,b]:
  rig['layers']=[v for v in rig['layers'] if not v[0].startswith('arm8_')];rig.pop('shoulders')
  for k in ['arm8_l','arm8_r']:rig['urls'].pop(k)
 for k in ['arm8_l','arm8_r']:
  im=np.array(Image.open(p/f'{n}_{k}_round10.png'))
  labels,_=label(im[:,:,3]>64);sizes=np.bincount(labels.ravel())[1:]
  counts[k]=int((sizes>100).sum())
 report['characters'][n]={'faceBodyInstrumentAndOtherPartsUnchanged':a==b,'armPawConnectedComponents':counts}
 assert a==b and all(v==1 for v in counts.values())
report['sceneMotionCodeUnchanged']=re.sub(pattern,'RIG_DATA',old)==re.sub(pattern,'RIG_DATA',new)
assert report['oldFilesPreserved'] and report['sceneMotionCodeUnchanged']
(p/'round10_scope_check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
