from pathlib import Path
import hashlib,json
base=Path(__file__).parent
root=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
path=base/'manifest.json';manifest=json.loads(path.read_text(encoding='utf8'))
for name in manifest:manifest[name]=hashlib.sha256((root/name).read_bytes()).hexdigest() if (root/name).exists() else None
path.write_text(json.dumps(manifest,indent=2),encoding='utf8')
