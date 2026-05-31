import sys, time, re, openpyxl
sys.stdout.reconfigure(encoding='utf-8')
from datetime import date
from collections import Counter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

XLSX = r'C:\Users\Shaul\Documents\job-search\outreach_list.xlsx'
SEARCH_TEXT = 'Thanks for connecting'

def slug(url):
    m = re.search(r'linkedin\.com/in/([^/?#]+)', str(url or '').lower())
    return m.group(1).rstrip('/') if m else None

def connect_browser():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    return webdriver.Chrome(options=options)

def load_xlsx():
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    return wb, ws, headers

def update_status(ws, headers, target_slug, new_status):
    li_col = headers.index('LinkedIn URL') + 1
    st_col = headers.index('Status') + 1
    dt_col = headers.index('Date Sent') + 1
    for i in range(2, ws.max_row + 1):
        s = slug(ws.cell(i, li_col).value)
        if s == target_slug:
            old = ws.cell(i, st_col).value
            ws.cell(i, st_col).value = new_status
            ws.cell(i, dt_col).value = str(date.today())
            return old
    return None

def get_conv_list(driver):
    """Return list of {threadUrl, name} for all conversations in the left panel."""
    return driver.execute_script(
        "var res=[];var seen=new Set();"
        # checkboxes exist in normal inbox view
        "var cbs=document.querySelectorAll('input.msg-selectable');"
        "cbs.forEach(function(cb){"
        "  var li=cb.closest('li');if(!li||seen.has(li))return;"
        "  seen.add(li);"
        "  var name=(li.innerText||'').split('\\n')[0].trim();"
        "  var a=li.querySelector('a[href]');"
        "  res.push({name:name.substring(0,50),href:(a&&a.href)||''});"
        "});"
        # fallback: any li inside the conversations container
        "if(res.length===0){"
        "  var c=document.querySelector('.msg-conversations-container');"
        "  if(c){c.querySelectorAll('li').forEach(function(li){"
        "    if(seen.has(li))return;seen.add(li);"
        "    var name=(li.innerText||'').split('\\n')[0].trim();"
        "    if(name.length>2&&name.length<60)res.push({name:name,href:''});"
        "  });}"
        "}"
        "return res;"
    )

def click_conv(driver, i):
    """Click the i-th conversation item. Returns name or None."""
    return driver.execute_script(
        "var seen=[];var seenEls=new Set();"
        # try checkbox-based items first
        "var cbs=document.querySelectorAll('input.msg-selectable');"
        "cbs.forEach(function(cb){"
        "  var li=cb.closest('li');if(li&&!seenEls.has(li)){seenEls.add(li);seen.push(li);}"
        "});"
        # fallback: li elements inside container
        "if(seen.length===0){"
        "  var c=document.querySelector('.msg-conversations-container');"
        "  if(c){c.querySelectorAll('li').forEach(function(li){"
        "    var name=(li.innerText||'').split('\\n')[0].trim();"
        "    if(name.length>2&&!seenEls.has(li)){seenEls.add(li);seen.push(li);}"
        "  });}"
        "}"
        "var li=seen[arguments[0]];if(!li)return null;"
        "var name=(li.innerText||'').split('\\n')[0].trim();"
        "var link=li.querySelector('a[href],button');if(link)link.click();else li.click();"
        "return name||'?';",
        i
    )

def conversation_has_search_text(driver, text):
    """Check if the open conversation contains the search text (in sent messages)."""
    return driver.execute_script(
        "var msgs=document.querySelectorAll("
        "  '.msg-s-event-list .msg-s-event-listitem, "
        "   .msg-s-message-list .msg-s-message-list-content, "
        "   [class*=\"msg-s-event\"]'"
        ");"
        "var t=arguments[0].toLowerCase();"
        "for(var m of msgs){"
        "  if((m.innerText||'').toLowerCase().indexOf(t)>-1)return true;"
        "}"
        # broader fallback
        "return document.body.innerText.toLowerCase().indexOf(t)>-1;",
        text
    )

def get_profile_from_conversation(driver):
    """Extract /in/ profile URL from the open conversation right panel."""
    links = driver.execute_script(
        "var found=[];"
        "var sels=['.msg-thread__link-to-profile',"
        "'.msg-entity-lockup__entity-title a',"
        "'.presence-entity__link',"
        "'.msg-s-event-listitem__link'];"
        "sels.forEach(function(sel){"
        "  document.querySelectorAll(sel).forEach(function(el){"
        "    var h=(el.href||'').split('?')[0].replace(/[/]+$/,'');"
        "    if(h.indexOf('/in/')>-1&&h.indexOf('/search/')<0)found.push(h);"
        "  });"
        "});"
        "if(found.length===0){"
        "  var lp=document.querySelector('.msg-conversations-container');"
        "  document.querySelectorAll('a[href*=\"/in/\"]').forEach(function(a){"
        "    if(lp&&lp.contains(a))return;"
        "    var h=(a.href||'').split('?')[0].replace(/[/]+$/,'');"
        "    if(/linkedin\\.com\\/in\\/[^/]+$/.test(h)&&h.indexOf('/search/')<0)found.push(h);"
        "  });"
        "}"
        "return found;"
    )
    for url in links:
        s = slug(url)
        if s:
            return url
    return None

def scroll_conv_list(driver):
    driver.execute_script(
        "var p=document.querySelector('.msg-conversations-container__conversations-list,"
        "[class*=\"conversation-list\"],.scaffold-layout__list');"
        "if(p)p.scrollTop+=400;else window.scrollBy(0,400);"
    )

def main():
    print("מתחבר לכרום...")
    driver = connect_browser()

    print("עובר ל-Messaging...")
    driver.get("https://www.linkedin.com/messaging/")
    time.sleep(5)

    wb, ws, headers = load_xlsx()
    updated = 0
    processed_threads = set()
    processed_slugs = set()

    print(f"עובר על שיחות ומחפש '{SEARCH_TEXT}' — לחץ Ctrl+C לעצירה ושמירה\n")

    try:
        stall = 0
        while stall < 8:
            n = driver.execute_script(
                "var s=new Set();"
                "document.querySelectorAll('input.msg-selectable').forEach(function(cb){"
                "  var li=cb.closest('li');if(li)s.add(li);"
                "});"
                "return s.size;"
            )
            if n == 0:
                # fallback count
                n = driver.execute_script(
                    "var c=document.querySelector('.msg-conversations-container');"
                    "if(!c)return 0;"
                    "return Array.from(c.querySelectorAll('li'))"
                    "  .filter(function(li){var t=(li.innerText||'').split('\\n')[0].trim();return t.length>2&&t.length<60;}).length;"
                )

            found_new = False
            for i in range(n):
                prev_url = driver.current_url.split('?')[0].rstrip('/')

                conv_name = click_conv(driver, i)
                if not conv_name:
                    continue
                time.sleep(2)

                cur_url = driver.current_url.split('?')[0].rstrip('/')
                if cur_url in processed_threads or cur_url == prev_url:
                    continue

                found_new = True
                processed_threads.add(cur_url)

                if not conversation_has_search_text(driver, SEARCH_TEXT):
                    print(f"  -- {conv_name} (אין הודעה)")
                    continue

                profile_url = get_profile_from_conversation(driver)
                if not profile_url:
                    print(f"  !: {conv_name} — יש הודעה אבל לא נמצא פרופיל")
                    continue

                s = slug(profile_url)
                if not s or s in processed_slugs:
                    continue
                processed_slugs.add(s)

                old = update_status(ws, headers, s, 'Message Sent')
                if old is not None:
                    print(f"  OK: {conv_name} ({old} -> Message Sent)")
                    updated += 1
                else:
                    print(f"  ?: {conv_name} ({s}) — לא בקובץ")

            if not found_new:
                stall += 1
                scroll_conv_list(driver)
                time.sleep(1.5)
            else:
                stall = 0

            # Go back to full inbox after processing a batch
            driver.get("https://www.linkedin.com/messaging/")
            time.sleep(3)

    except KeyboardInterrupt:
        print(f"\nנעצר.")

    wb.save(XLSX)

    wb2 = openpyxl.load_workbook(XLSX)
    ws2 = wb2.active
    h2 = [c.value for c in ws2[1]]
    sc2 = h2.index('Status') + 1
    counts = Counter(ws2.cell(i, sc2).value for i in range(2, ws2.max_row + 1))
    print(f"\nנשמר. עודכנו: {updated}")
    print(f"Sent: {counts.get('Sent',0)} | Message Sent: {counts.get('Message Sent',0)} | Pending: {counts.get('Pending',0)}")

if __name__ == '__main__':
    main()
