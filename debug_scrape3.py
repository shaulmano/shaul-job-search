import sys
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver

def connect():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

driver = connect()

cards = driver.execute_script("""
    var results = [];
    var links = document.querySelectorAll('a[href*="/in/"]');
    var seen = new Set();
    for (var link of links) {
        var href = link.href.split('?')[0].replace(/\\/+$/, '');
        if (!href.includes('/in/') || seen.has(href)) continue;
        // Walk up to find the card (look for a container with decent text)
        var node = link;
        var cardText = '';
        for (var i = 0; i < 8; i++) {
            node = node.parentElement;
            if (!node) break;
            var t = node.innerText || '';
            if (t.length > 30) { cardText = t; break; }
        }
        seen.add(href);
        results.push({url: href, text: cardText.substring(0, 300)});
    }
    return results;
""")

for c in cards[:5]:
    print("URL:", c['url'])
    print("TEXT:", repr(c['text']))
    print()
