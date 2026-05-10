"""
Headless Playwright QA: tests all dashboard pages at mobile/tablet/desktop viewports.
Saves screenshots to /tmp/qa_*.png and prints pass/fail checks.
"""
import asyncio
from playwright.async_api import async_playwright

BASE = "http://localhost:8765"

VIEWPORTS = [
    ("mobile_390",  390,  844),
    ("tablet_768",  768, 1024),
    ("desktop_1280", 1280, 900),
]

PAGES = [
    ("index",    f"{BASE}/index.html"),
    ("openings", f"{BASE}/openings.html"),
    ("families", f"{BASE}/families.html"),
    ("opening",  f"{BASE}/opening.html?eco=A18"),
]

checks_passed = 0
checks_failed = 0

def ok(msg):
    global checks_passed
    print(f"  ✓ {msg}")
    checks_passed += 1

def fail(msg):
    global checks_failed
    print(f"  ✗ FAIL: {msg}")
    checks_failed += 1

async def check_nav(page, vp_name, pg_name):
    """Nav hamburger visible on mobile, hidden on desktop."""
    toggle_display = await page.evaluate(
        "() => getComputedStyle(document.querySelector('.nav-toggle')).display"
    )
    if vp_name.startswith("mobile"):
        if toggle_display != "none":
            ok(f"{pg_name} nav hamburger visible on {vp_name}")
        else:
            fail(f"{pg_name} nav hamburger should be visible on {vp_name}, got display:{toggle_display}")
    else:
        if toggle_display == "none":
            ok(f"{pg_name} nav hamburger hidden on {vp_name}")
        else:
            fail(f"{pg_name} nav hamburger should be hidden on {vp_name}, got display:{toggle_display}")

async def check_icon(page, pg_name):
    logo = await page.query_selector('.brand-logo')
    if logo:
        ok(f"{pg_name} brand logo present")
    else:
        fail(f"{pg_name} brand logo missing")

async def check_no_horizontal_overflow(page, vp_name, pg_name):
    overflow = await page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
    if overflow:
        fail(f"{pg_name} @ {vp_name}: horizontal overflow detected")
    else:
        ok(f"{pg_name} @ {vp_name}: no horizontal overflow")

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for vp_name, width, height in VIEWPORTS:
            print(f"\n=== {vp_name} ({width}×{height}) ===")
            ctx = await browser.new_context(viewport={"width": width, "height": height})

            for pg_name, url in PAGES:
                print(f"\n  -- {pg_name} --")
                page = await ctx.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=15000)
                    await page.wait_for_timeout(800)

                    # Nav checks
                    await check_nav(page, vp_name, pg_name)
                    await check_icon(page, pg_name)

                    # Overflow check
                    await check_no_horizontal_overflow(page, vp_name, pg_name)

                    # Page-specific checks
                    if pg_name == "opening":
                        # Plotly chart rendered
                        chart = await page.query_selector('.js-plotly-plot')
                        if chart:
                            ok(f"{pg_name} Plotly chart rendered on {vp_name}")
                        else:
                            fail(f"{pg_name} Plotly chart missing on {vp_name}")

                        # Engine cards present
                        cards = await page.query_selector('.engine-cards')
                        if cards:
                            ok(f"{pg_name} engine-cards present on {vp_name}")
                        else:
                            fail(f"{pg_name} engine-cards missing on {vp_name}")

                        # On mobile, engine cards should be 1-col
                        if vp_name.startswith("mobile"):
                            cols = await page.evaluate(
                                "() => getComputedStyle(document.querySelector('.engine-cards')).gridTemplateColumns"
                            )
                            # single column = one value, no space in template cols value
                            if cols and cols.count(" ") == 0:
                                ok(f"engine-cards 1-col on {vp_name}: {cols}")
                            else:
                                fail(f"engine-cards should be 1-col on mobile, got: {cols}")

                        # Board present
                        board = await page.query_selector('#opening-board')
                        if board:
                            ok(f"{pg_name} chess board present on {vp_name}")
                        else:
                            fail(f"{pg_name} chess board missing on {vp_name}")

                    if pg_name == "openings":
                        # Table scroll wrapper
                        wrap = await page.query_selector('.table-scroll-wrap')
                        if wrap:
                            ok(f"{pg_name} table-scroll-wrap present")
                        else:
                            fail(f"{pg_name} table-scroll-wrap missing")

                    # Screenshot
                    shot_path = f"/tmp/qa_{vp_name}_{pg_name}.png"
                    await page.screenshot(path=shot_path, full_page=True)
                    print(f"  📷 {shot_path}")

                except Exception as e:
                    fail(f"{pg_name} @ {vp_name} exception: {e}")
                finally:
                    await page.close()

            await ctx.close()

        await browser.close()

    print(f"\n{'='*40}")
    print(f"PASSED: {checks_passed}  FAILED: {checks_failed}")
    if checks_failed == 0:
        print("ALL CHECKS PASSED ✓")
    else:
        print("SOME CHECKS FAILED — see above")

asyncio.run(run())
