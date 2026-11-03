from pathlib import Path
root=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
s=(root/'scripts/verify_birthday_lifecycle.py').read_text(encoding='utf8')
s=s[:s.index("    result['ios_shape']")]
s=s.replace('ROOT=Path(__file__).resolve().parents[1]',f'ROOT=Path({str(root)!r})')
s=s.replace("page.wait_for_function('!document.documentElement.hasAttribute(\"data-bday-intro\")')", "print('SEEK',page.evaluate('()=>({time:__birthday.audio.audio.currentTime,d:__birthday.audio.diagnostics(),ready:document.documentElement.outerHTML.slice(0,300)})'));page.wait_for_timeout(1000);print('AFTER',page.evaluate('()=>({time:__birthday.audio.audio.currentTime,d:__birthday.audio.diagnostics()})'))")
exec(s)
