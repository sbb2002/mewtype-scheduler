import sys
from playwright.sync_api import sync_playwright
out=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch()
    for dev,vp,mob in (("pc",(1440,900),False),("mobile",(390,844),True)):
        for th in ("dark","light"):
            c=b.new_context(viewport={"width":vp[0],"height":vp[1]},is_mobile=mob,has_touch=mob,device_scale_factor=2 if mob else 1)
            c.add_init_script("localStorage.setItem('theme','%s')"%th)
            c.route("**/data/*.json",lambda r:r.fulfill(response=c.request.get("https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"+r.request.url.split("/data/")[1])))
            pg=c.new_page(); pg.goto("http://localhost:8099/?va=claude"); pg.wait_for_timeout(4000)
            # 카드 팝업
            if not mob:
                sel=".tt-blk"
            else:
                try: pg.locator("text=이후 예고").first.click(timeout=3000); pg.wait_for_timeout(500)
                except Exception as e: print("expand fail")
                sel=".wk2__dot"
            n=pg.locator(sel).count(); print(dev,th,sel,n)
            if n:
                try:
                    pg.locator(sel).first.click(timeout=3000); pg.wait_for_timeout(800)
                except Exception as e: print("click fail",str(e)[:100])
            print(" tt-pop",pg.locator(".tt-pop").count())
            pg.screenshot(path=f"{out}/{dev}_{th}_popup_card.png")
            pg.keyboard.press("Escape"); pg.mouse.click(5,5); pg.wait_for_timeout(400)
            # 플레이어 팝업
            btn=pg.locator(".player-btn:not(.week-btn)")
            print(" player-btn",btn.count())
            if btn.count():
                try: btn.first.click(timeout=3000); pg.wait_for_timeout(2000)
                except Exception as e: print("pbtn fail",str(e)[:100])
            print(" mp-pop",pg.locator(".mp-pop").count())
            pg.screenshot(path=f"{out}/{dev}_{th}_popup_player.png")
            c.close()
    b.close()
