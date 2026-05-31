from selenium import webdriver

options = webdriver.ChromeOptions()
options.add_experimental_option('debuggerAddress', '127.0.0.1:9222')
driver = webdriver.Chrome(options=options)

print('URL:', driver.current_url)
print('Title:', driver.title)
print()

# Find profile links
links = driver.find_elements('css selector', 'a[href*="/in/"]')
print(f'Profile links found: {len(links)}')
for l in links[:10]:
    href = l.get_attribute('href') or ''
    text = l.text.strip()[:80]
    print(f'  {href}')
    print(f'  text: {text}')
    print()

# Find common result containers
for sel in [
    '.reusable-search__result-container',
    '.entity-result',
    'li.artdeco-list__item',
    '.search-results__list li',
    '[data-chameleon-result-urn]',
]:
    els = driver.find_elements('css selector', sel)
    print(f'Selector "{sel}": {len(els)} elements')
