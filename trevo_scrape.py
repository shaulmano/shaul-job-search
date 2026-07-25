import sys, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Credentials live in config.py, which is gitignored — this repo is public.
from config import LINKEDIN_EMAIL as TREVO_EMAIL, LINKEDIN_PASSWORD as TREVO_PASSWORD

sys.stdout.reconfigure(encoding='utf-8')

OUT = Path(r"C:\Users\Shaul\Documents\job-search")

def scrape():
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        page = browser.new_page()

        # ── Login ──
        page.goto("https://trevo.work/login")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.fill('#email', TREVO_EMAIL)
        page.fill('#password', TREVO_PASSWORD)
        time.sleep(0.5)
        page.screenshot(path=str(OUT / "trevo_login_filled.png"))

        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        print("After login:", page.url)
        page.screenshot(path=str(OUT / "trevo_after_login.png"))
        results["after_login_url"] = page.url

        if "login" in page.url:
            results["login_error"] = page.inner_text("body")[:500]
            print("LOGIN FAILED")
            browser.close()
            return

        print("LOGIN SUCCESS!")

        # ── Collect all nav tab hrefs ──
        page.goto("https://trevo.work/account/matches")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        results["matches_text"] = page.inner_text("body")[:12000]
        page.screenshot(path=str(OUT / "trevo_matches.png"), full_page=False)

        nav_links = page.evaluate("""() => {
            return [...document.querySelectorAll('a[href]')]
                .filter(a => a.href.includes('trevo.work/account') && a.offsetParent !== null)
                .map(a => ({text: a.innerText.trim(), href: a.href}))
                .filter(t => t.text.length > 0 && t.text.length < 30);
        }""")
        results["nav_links"] = nav_links
        print("Nav links found:", len(nav_links))

        visited = set()
        for item in nav_links:
            href = item["href"]
            if href in visited or not href:
                continue
            visited.add(href)
            name = item["text"][:20].replace(" ", "_")
            try:
                page.goto(href, timeout=10000)
                page.wait_for_load_state("networkidle", timeout=6000)
                time.sleep(2)
                if "login" not in page.url:
                    text = page.inner_text("body")[:6000]
                    results[f"tab_{name}"] = {"url": page.url, "text": text}
                    safe_name = "".join(c if c.isascii() and c.isalnum() else "_" for c in name)
                    page.screenshot(path=str(OUT / f"trevo_{safe_name}.png"))
                    print(f"  tab '{name}': {page.url}")
            except Exception as e:
                print(f"  tab '{name}' error: {e}")

        browser.close()

    out_file = OUT / "trevo_data.json"
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone. Saved to {out_file}")

if __name__ == "__main__":
    scrape()
