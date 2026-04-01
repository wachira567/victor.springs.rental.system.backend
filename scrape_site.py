import json
import time
from playwright.sync_api import sync_playwright

def run():
    print("Starting Playwright...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        print("Navigating to login page...")
        page.goto("https://tolet.co.ke/login", timeout=60000)
        
        try:
            print("Looking for email input...")
            page.wait_for_selector("input[type='email'], input[name='username'], input[name='email']", timeout=10000)
            page.fill("input[type='email'], input[name='username'], input[name='email']", "wachiramboche@gmail.com")
            
            print("Looking for password input...")
            page.fill("input[type='password'], input[name='password']", "Awesome@15")
            
            submit_selectors = "button[type='submit'], input[type='submit'], .btn-primary, button:has-text('Login')"
            page.click(submit_selectors)
            print("Submitted login form.")
        except Exception as e:
            print("Failed to fill login form:", e)
            return
            
        print("Waiting for dashboard to load...")
        try:
            page.wait_for_selector('aside, .main-sidebar, .sidebar-menu, .nav-sidebar, #sidebar', timeout=20000)
        except Exception as e:
            print("Timeout waiting for sidebar. Might be a 2FA or slow load?", e)
            print(page.content()[:1000])
            
        time.sleep(3)
        
        print("Extracting sidebar menus...")
        tree = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('aside a, .sidebar a, .main-menu a, .sidebar-menu a'));
            const data = [];
            for(let a of links) {
                const text = a.innerText.replace(/\\n/g, ' ').trim();
                const url = a.href;
                if (!text) continue;
                
                // Determine if it's a submenu item
                let isSub = false;
                let parentText = null;
                const grandParentLi = a.closest('ul') ? a.closest('ul').closest('li') : null;
                if (grandParentLi) {
                    const pLink = grandParentLi.querySelector('a');
                    if (pLink) {
                        parentText = pLink.innerText.replace(/\\n/g, ' ').trim();
                        isSub = true;
                    }
                }
                
                data.push({
                    name: text,
                    url: url.startsWith('javascript') || url === '#' ? null : url,
                    parent: isSub && parentText !== text ? parentText : null
                });
            }
            return data;
        }""")
        
        organized = {}
        for item in tree:
            name = item['name']
            url = item['url']
            parent = item['parent']
            
            if parent:
                if parent not in organized:
                    organized[parent] = {'url': None, 'subpages': []}
                # Check if not dup
                if not any(x['name'] == name for x in organized[parent]['subpages']):
                    organized[parent]['subpages'].append({'name': name, 'url': url})
            else:
                if name not in organized:
                    organized[name] = {'url': url, 'subpages': []}
                elif url:
                    organized[name]['url'] = url
                    
        # Remove empty or irrelevant items
        clean_menus = {k: v for k, v in organized.items() if k and (v['url'] or v['subpages'])}
        
        with open("tolet_menu_structure.json", "w") as f:
            json.dump(clean_menus, f, indent=4)
            
        print(f"Saved {len(clean_menus)} main menu items to tolet_menu_structure.json")
        
        # Scrape buttons on the first 10 pages for discovery
        valid_urls = []
        for name, data in clean_menus.items():
            if data['url'] and 'http' in data['url'] and 'logout' not in data['url'].lower():
                valid_urls.append((name, data['url']))
            for sub in data['subpages']:
                if sub['url'] and 'http' in sub['url'] and 'logout' not in sub['url'].lower():
                    valid_urls.append((f"{name} > {sub['name']}", sub['url']))
                    
        print(f"Discovered {len(valid_urls)} pages. Fetching specific features from the first 5...")
        
        page_features = {}
        for title, url in valid_urls[:5]:
            print(f"  Scraping: {title} ({url})")
            try:
                page.goto(url, timeout=15000)
                page.wait_for_load_state("networkidle", timeout=5000)
                buttons = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('.btn, button, input[type="submit"], a.btn'));
                    return btns.map(b => b.innerText.trim() || b.title || b.value).filter(t => t && t.length > 0 && t.length < 50);
                }""")
                tables = page.evaluate("""() => {
                    const ths = Array.from(document.querySelectorAll('th'));
                    return ths.map(t => t.innerText.trim()).filter(t => t && t.length > 0);
                }""")
                page_features[title] = {
                    'buttons': list(set(buttons)),
                    'table_columns': list(set(tables))
                }
            except Exception as e:
                print(f"  -> Error loading {url}: {e}")
                
        with open("tolet_page_features.json", "w") as f:
            json.dump(page_features, f, indent=4)
            
if __name__ == "__main__":
    run()
