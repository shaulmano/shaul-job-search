const { chromium } = require('playwright');
const fs = require('fs');

// This repo is public — credentials come from the environment, never the source.
const TREVO_EMAIL = process.env.TREVO_EMAIL;
const TREVO_PASSWORD = process.env.TREVO_PASSWORD;
if (!TREVO_EMAIL || !TREVO_PASSWORD) {
  console.error('Set TREVO_EMAIL and TREVO_PASSWORD before running.');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 500 });
  const page = await browser.newPage();

  const results = {};

  try {
    // Login
    await page.goto('https://trevo.work/account/login');
    await page.waitForLoadState('networkidle');

    // Fill login form
    await page.fill('input[type="email"], input[name="email"], input[placeholder*="mail"]', TREVO_EMAIL);
    await page.fill('input[type="password"], input[name="password"], input[placeholder*="password"], input[placeholder*="סיסמ"]', TREVO_PASSWORD);
    await page.click('button[type="submit"], button:has-text("התחבר"), button:has-text("Login"), button:has-text("Sign in")');

    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    console.log('After login URL:', page.url());

    // Go to matches page
    await page.goto('https://trevo.work/account/matches');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    results['matches_url'] = page.url();
    results['matches_title'] = await page.title();

    // Get page text
    results['matches_text'] = await page.evaluate(() => document.body.innerText);

    // Screenshot
    await page.screenshot({ path: 'C:\\Users\\Shaul\\Documents\\job-search\\trevo_matches.png', fullPage: false });

    // Find all tab links
    const tabs = await page.evaluate(() => {
      const links = [...document.querySelectorAll('nav a, [role="tab"], .tab, [class*="tab"] a, a[href*="account"]')];
      return links.map(el => ({ text: el.innerText?.trim(), href: el.href || el.getAttribute('href') })).filter(t => t.text && t.href);
    });
    results['tabs'] = tabs;
    console.log('Tabs found:', JSON.stringify(tabs, null, 2));

    // Try to visit key tabs
    const tabsToVisit = [
      { name: 'new', paths: ['/account/new', '/account/what-new', '/account/feed'] },
      { name: 'tracking', paths: ['/account/tracking', '/account/pipeline', '/account/applied'] },
      { name: 'interview', paths: ['/account/interview', '/account/interviews'] },
      { name: 'searches', paths: ['/account/searches', '/account/search'] },
      { name: 'cv', paths: ['/account/cv', '/account/resume'] },
      { name: 'settings', paths: ['/account/settings', '/account/preferences'] },
    ];

    for (const tab of tabsToVisit) {
      for (const path of tab.paths) {
        try {
          await page.goto('https://trevo.work' + path);
          await page.waitForLoadState('networkidle');
          await page.waitForTimeout(1500);
          if (!page.url().includes('login')) {
            results[tab.name + '_text'] = await page.evaluate(() => document.body.innerText);
            results[tab.name + '_url'] = page.url();
            await page.screenshot({ path: `C:\\Users\\Shaul\\Documents\\job-search\\trevo_${tab.name}.png`, fullPage: false });
            break;
          }
        } catch(e) { /* skip */ }
      }
    }

    // Also click through visible tabs on the matches page
    await page.goto('https://trevo.work/account/matches');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const clickableTabs = await page.evaluate(() => {
      const items = [...document.querySelectorAll('a, button')];
      return items.filter(el => {
        const txt = el.innerText?.trim();
        return txt && txt.length < 30 && (
          txt.includes('חדש') || txt.includes('מעקב') || txt.includes('ראיון') ||
          txt.includes('סדרגו') || txt.includes('חיפוש') || txt.includes('הגדרות') ||
          txt.includes('CV') || txt.includes('העשרה') || txt.includes('תשלום')
        );
      }).map(el => ({ text: el.innerText?.trim(), href: el.href || '', tag: el.tagName }));
    });
    results['clickable_tabs'] = clickableTabs;
    console.log('Clickable tabs:', JSON.stringify(clickableTabs, null, 2));

  } catch(e) {
    results['error'] = e.message;
    console.error('Error:', e.message);
  }

  fs.writeFileSync('C:\\Users\\Shaul\\Documents\\job-search\\trevo_data.json', JSON.stringify(results, null, 2));
  console.log('Done! Data saved.');

  await browser.close();
})();
