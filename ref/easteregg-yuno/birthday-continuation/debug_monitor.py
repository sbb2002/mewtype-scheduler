from pathlib import Path
root=Path(r'C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/feat-birthday-music-scene')
s=(root/'scripts/verify_monitor_birthday.py').read_text(encoding='utf8')
s=s.replace('ROOT=Path(__file__).resolve().parents[1]',f'ROOT=Path({str(root)!r})')
s=s.replace("page.on('pageerror',lambda e:errors.append(str(e)))", """page.on('pageerror',lambda e:errors.append(str(e)))
   page.add_init_script(\"window.pointerTrace=[];for(const name of ['pointerdown','pointermove','pointerup','lostpointercapture'])document.addEventListener(name,e=>pointerTrace.push({type:name,x:e.clientX,y:e.clientY,id:e.pointerId,primary:e.isPrimary,buttons:e.buttons,target:e.target.className}),true)\")""")
s=s.replace("assert page.locator('#reset-dlg').get_attribute('data-bday-edge')==direction,direction", "assert page.locator('#reset-dlg').get_attribute('data-bday-edge')==direction,dict(name=name,direction=direction,start=start,end=end,rect=r,errors=errors,trace=page.evaluate('pointerTrace.slice(-25)'))")
exec(s)
