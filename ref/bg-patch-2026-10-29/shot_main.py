import sys
from playwright.sync_api import sync_playwright
out=sys.argv[1]
with sync_playwright() as p:
    b=p.chromium.launch()
    for dev,vp,mob in (("pc",(1440,900),False),("mobile",(390,844),True)):
        for th in ("dark","light"):
            c=b.new_context(viewport={"width":vp[0],"height":vp[1]},is_mobile=mob,has_touch=mob,device_scale_factor=2 if mob else 1)
            c.add_init_script("localStorage.setItem('theme','%s')"%th)
            c.route("**/data/*.json",lambda r:r.fulfill(response=c.request.get("https://raw.githubusercontent.com/sbb2002/mewtype-scheduler-data/data/"+r.request.url.split("/data/")[1]))); pg=c.new_page(); pg.goto("http://localhost:8099/?va=claude"); pg.wait_for_timeout(4000)
            pg.screenshot(path=f"{out}/{dev}_{th}_main.png")
            for sel in (".tcard",".card",".k-card"):
                if pg.locator(sel).count():
                    try:
                        pg.locator(sel).first.click(timeout=3000); pg.wait_for_timeout(800)
                        print(dev,th,"clicked",sel,pg.locator(".tt-pop").count())
                    except Exception as e: print("fail",sel,str(e)[:80])
                    break
            pg.screenshot(path=f"{out}/{dev}_{th}_popup.png")
            c.close()
    b.close()
