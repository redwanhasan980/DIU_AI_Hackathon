# Re-capture README screenshots: run `make demo` in another terminal, then
#   .venv/bin/python docs/screenshots/capture.py
# Needs `pip install playwright` and a Chromium (set CHROME to its path if not the default).
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
OUT = str(Path(__file__).resolve().parent)
SHOTS=[("/", "light", "en", 1280, 900, False, "01-network.png"),
       ("/agents/AG00433", "light", "en", 1280, 1180, False, "02-agent-detail.png"),
       ("/agents/AG00433", "dark", "bn", 1280, 720, False, "03-agent-detail-bangla-dark.png"),
       ("/dso?dso=DSO025", "light", "en", 1280, 900, False, "04-dso-plan.png"),
       ("/impact", "light", "en", 1280, 1100, False, "05-impact.png"),
       ("/card/AG00433", "light", "bn", 390, 800, False, "06-agent-card-bangla.png")]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        for path, theme, lang, w, h, full, name in SHOTS:
            ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=theme, device_scale_factor=1)
            await ctx.add_init_script(f"localStorage.setItem('fw.lang','{lang}')")
            page = await ctx.new_page()
            await page.goto("http://localhost:8000" + path); await page.wait_for_timeout(2500)
            await page.screenshot(path=f"{OUT}/{name}", full_page=full)
            await ctx.close(); print(name)
        await b.close()
asyncio.run(main())
