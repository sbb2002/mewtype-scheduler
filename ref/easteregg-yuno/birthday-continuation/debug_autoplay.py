from pathlib import Path
root=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
s=(root/'scripts/verify_birthday_lifecycle.py').read_text(encoding='utf8')
s=s[:s.index("    page.tap('.bday-start')")]
s=s.replace('ROOT=Path(__file__).resolve().parents[1]',f'ROOT=Path({str(root)!r})')
s=s.replace("page.locator('.bday-start').wait_for(state='visible');page.wait_for_timeout(200)","page.wait_for_timeout(2000)")
s+="\n    print('DETAIL',page.evaluate('()=>({d:__birthday.audio.diagnostics(),time:__birthday.audio.audio.currentTime,paused:__birthday.audio.paused})'));print(errors)\n"
exec(s)
