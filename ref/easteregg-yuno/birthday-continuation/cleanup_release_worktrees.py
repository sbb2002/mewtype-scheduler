from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[2]
base=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4').resolve(strict=True)
for name in ['feat-birthday-music-scene','docs-birthday-music-release']:
 target=(base/name).resolve(strict=True)
 assert target.parent==base and target.name==name,'워크트리 경로 범위가 다름'
 status=subprocess.check_output(['git','status','--porcelain'],cwd=target,text=True).strip()
 assert not status,f'미보존 변경이 있어 삭제 중단: {target}'
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=target,text=True).strip()
 subprocess.check_call(['git','merge-base','--is-ancestor',head,'main'],cwd=root)
 print('병합·깨끗한 상태와 절대 경로 확인:',target)
 subprocess.check_call(['git','worktree','remove',str(target)],cwd=root)
