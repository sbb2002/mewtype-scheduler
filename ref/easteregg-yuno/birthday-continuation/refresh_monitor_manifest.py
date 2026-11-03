from pathlib import Path
import json,hashlib
B=Path(__file__).parent;D=B/'monitor-delivery';R=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
m={}
for p in D.rglob('*'):
 if p.is_file():
  n=p.relative_to(D).as_posix();m[n]=hashlib.sha256((R/n).read_bytes()).hexdigest() if (R/n).exists() else None
(B/'monitor-manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8')
