import sys
sys.stdout.reconfigure(encoding='utf-8')
from selenium import webdriver
from selenium.webdriver.common.by import By
import time

options = webdriver.ChromeOptions()
options.add_experimental_option('debuggerAddress', '127.0.0.1:9222')
driver = webdriver.Chrome(options=options)

driver.get('https://www.linkedin.com/in/einam-trivizki-182a88323')
time.sleep(4)

coords = driver.execute_script("""
    for (var el of document.querySelectorAll('div, span, button')) {
        var t = (el.innerText || '').trim().toLowerCase();
        if (t !== 'connect' && t !== 'התחבר') continue;
        if (el.closest('nav') || el.closest('aside')) continue;
        var r = el.getBoundingClientRect();
        if (r.width === 0 || r.top < 70 || r.top > 700) continue;
        el.scrollIntoView({block:'center', behavior:'instant'});
        r = el.getBoundingClientRect();
        return {x: r.left + r.width/2, y: r.top + r.height/2};
    }
    return null;
""")
print(f'Connect coords: {coords}')
if not coords:
    print('No connect button found')
    driver.quit()
    exit()

for event in ('mouseMoved', 'mousePressed', 'mouseReleased'):
    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
        'type': event, 'x': coords['x'], 'y': coords['y'],
        'button': 'none' if event == 'mouseMoved' else 'left',
        'clickCount': 0 if event == 'mouseMoved' else 1,
        'modifiers': 0, 'pointerType': 'mouse',
    })
time.sleep(3)

elements = driver.execute_script("""
    var result = [];
    document.querySelectorAll('textarea, input, [contenteditable]').forEach(function(el) {
        var r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) {
            result.push({
                tag: el.tagName,
                name: el.getAttribute('name') || '',
                id: el.id || '',
                placeholder: el.getAttribute('placeholder') || '',
                aria: el.getAttribute('aria-label') || '',
                contenteditable: el.getAttribute('contenteditable') || '',
                top: Math.round(r.top)
            });
        }
    });
    return result;
""")
print('\\nVisible input elements after clicking Connect:')
for e in elements:
    print(e)

input('Press Enter to close...')
driver.quit()
