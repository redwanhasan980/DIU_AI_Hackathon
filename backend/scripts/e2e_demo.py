"""End-to-end check of the SRS §14 demo script in a real browser.

Start the app first (`make demo`), then:
    pip install playwright && playwright install chromium     # once
    python scripts/e2e_demo.py [--url http://localhost:8000] [--chrome /path/to/chrome]

Every step asserts what a judge would see; the script exits non-zero on the first failure.
Note: it records one approval in artifacts/decisions.json (git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

from playwright.async_api import Page, async_playwright

DEMO_AGENT = "AG00471"  # Rahmania Bhandar, Sylhet — rural remittance (see CLAUDE.md)
BN = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def lakh(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + groups) + "," + tail


def api(url: str, path: str) -> dict:
    with urllib.request.urlopen(f"{url}/api/v1{path}") as r:
        return json.loads(r.read())


async def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail else ''}")
    if not ok:
        raise SystemExit(1)


async def text(page: Page) -> str:
    return await page.locator("main").inner_text()


async def run(url: str, chrome: str | None) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        async def go(path: str) -> str:
            await page.goto(url + path)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)
            return await text(page)

        # 1. Network map on the demo date, 5 days before Eid
        t = await go("/")
        await check("network: Eid banner", "Eid-ul-Fitr in 5 days" in t)
        await check(
            "network: KPI tiles", "Agents needing action tomorrow" in t and "Backtest: fewer stockouts" in t
        )
        markers = await page.locator("path.leaflet-interactive").count()
        await check("network: agent markers on the map", markers >= 400, f"{markers} markers")

        # expected values come from the API, so the script never goes stale when the model is retrained
        agent = api(url, f"/agents/{DEMO_AGENT}")["agent"]
        rec = api(url, f"/agents/{DEMO_AGENT}/recommendation")
        amount = "৳" + lakh(rec["amount"])

        # 2. Risk list -> demo agent
        t = await go(f"/risk?district={agent['district']}")
        await check(f"risk list: filtered to {agent['district']}", agent["shop_name"] in t)
        # shops can share a generic name, so pick the row by agent id
        await page.locator("tr", has_text=DEMO_AGENT).get_by_role("link").click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        t = await text(page)
        await check(
            "agent: recommendation",
            rec["action"] == "TOP_UP_CASH" and "Top up cash" in t and amount in t,
            amount,
        )
        await check("agent: reason codes + outlook", "Eid-ul-Fitr in 5 days" in t and "7-day outlook" in t)
        await check(
            "agent: forecast and drivers charts", await page.locator(".recharts-surface").count() >= 2
        )
        await check(
            "agent: explanation labelled and grounded", "explanation" in t.lower() and t.count(amount) >= 2
        )

        # 3. Bangla
        await page.get_by_role("button", name="বাংলা").click()
        await page.wait_for_timeout(1200)
        t = await text(page)
        await check("agent: Bangla explanation", "ঈদুল ফিতর" in t and amount.translate(BN) in t)
        await page.get_by_role("button", name="EN").click()
        await page.wait_for_timeout(600)

        # 4. Human approval
        await page.get_by_role("button", name="Approve").click()
        await page.wait_for_timeout(800)
        status = await page.get_by_role("status").inner_text()
        await check(
            "agent: approval recorded, nothing executed", "nothing is executed automatically" in status
        )

        # 5. DSO plan respects capacity
        t = await go("/dso")
        await check("dso: plan with ranked visits", "DSO visit plan" in t and "Cash to carry" in t)
        await page.get_by_label("Max visits").fill("3")
        await page.wait_for_timeout(1000)
        ranks = await page.locator("main ol > li").count()
        await check("dso: max visits = 3 is respected", ranks <= 3, f"{ranks} visits")

        # 6. Impact: cached backtest + live re-run
        t = await go("/impact")
        await check(
            "impact: status quo vs FloatWise", "Stockout agent-days" in t and "cached default run" in t
        )
        await page.get_by_role("button", name="Re-run simulation").click()
        await page.wait_for_timeout(5000)
        await check("impact: live re-run", "live run" in await text(page))

        # 7. Model & fairness
        t = await go("/model")
        await check(
            "model: 4 acceptance checks pass",
            t.count("pass") >= 4 and "fail" not in t.split("Forecast error")[0],
        )
        await check("model: fairness table", "No segment is worse than the baseline" in t)

        # 8. Decisions log + feedback summary
        t = await go("/decisions")
        await check("decisions: approval logged", DEMO_AGENT in t and "Approval rate" in t)

        # 9. Bangla agent card
        await page.get_by_role("button", name="বাংলা").click()
        t = await go(f"/card/{DEMO_AGENT}")
        await check("agent card: Bangla action", "নগদ এনে রাখুন" in t)
        await page.get_by_role("button", name="EN").click()

        # 10. Another date + dark mode
        await go("/")
        await page.get_by_label("Decision date").fill("2025-09-10")
        await page.wait_for_timeout(1500)
        t = await text(page)
        await check(
            "other date: network renders", "Agents needing action tomorrow" in t and "Eid-ul-Fitr in" not in t
        )
        await page.get_by_role("button", name="☾").click()
        theme = await page.evaluate("document.documentElement.getAttribute('data-theme')")
        await check("dark mode toggle", theme == "dark")

        await check("no JavaScript errors", not errors, "; ".join(errors[:3]))
        await browser.close()
    print("ALL DEMO STEPS PASSED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--chrome", default=None, help="path to a Chromium/Chrome binary (optional)")
    args = ap.parse_args()
    try:
        asyncio.run(run(args.url.rstrip("/"), args.chrome))
    except SystemExit as e:
        sys.exit(e.code)


if __name__ == "__main__":
    main()
