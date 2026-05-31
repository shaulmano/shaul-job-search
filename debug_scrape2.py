import sys
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.common.by import By

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

driver = connect()

# Get the outer HTML of the first result card to understand structure
result = driver.execute_script("""
    // Try to find the first result card
    var selectors = [
        'li.reusable-search__result-container',
        'li[class*="result"]',
        'div[data-view-name*="search"]',
        '.artdeco-list__item',
        'ul.reusable-search__entity-result-list li',
    ];
    for (var s of selectors) {
        var el = document.querySelector(s);
        if (el) return {selector: s, html: el.outerHTML.substring(0, 2000)};
    }
    // fallback: find first /in/ link parent
    var link = document.querySelector('a[href*="/in/"]');
    if (link) {
        var p = link;
        for (var i=0; i<5; i++) { p = p.parentElement; }
        return {selector: 'parent-5', html: p.outerHTML.substring(0, 2000)};
    }
    return null;
""")

if result:
    print(f"Selector: {result['selector']}")
    print(result['html'])
else:
    print("Nothing found")
