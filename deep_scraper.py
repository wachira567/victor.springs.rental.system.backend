import json
import time
from traceback import format_exc
from playwright.sync_api import sync_playwright

BASE_URL = "https://tolet.co.ke"

def extract_page_info(page):
    """
    Evaluates JavaScript on the page to extract:
    - Page titles
    - Visible form inputs/selects (to understand data schemas)
    - Tables and their column headers
    - Buttons and Links (especially Add/Edit)
    """
    return page.evaluate("""() => {
        const info = {
            title: document.title,
            header: document.querySelector('h1, h2, .page-title, .card-title, .box-title')?.innerText?.trim() || 'No Header',
            buttons: Array.from(document.querySelectorAll('.btn, button, input[type="submit"], a.btn, a[class*="btn-"]'))
                .map(b => ({
                    text: b.innerText?.trim() || b.title || b.value || b.getAttribute('aria-label'),
                    href: b.href || null,
                    type: b.type || b.tagName.toLowerCase(),
                    onclick: b.getAttribute('onclick')
                })).filter(b => b.text && b.text.length > 0 && b.text.length < 50),
            tables: Array.from(document.querySelectorAll('table')).map(table => {
                const headers = Array.from(table.querySelectorAll('th')).map(th => th.innerText?.trim()).filter(Boolean);
                // Grab the first row's action links to see if there's an Edit/View
                const firstRowLinks = Array.from(table.querySelectorAll('tbody tr:first-child a')).map(a => ({
                    text: a.innerText?.trim() || a.title || a.querySelector('i')?.className || 'link',
                    href: a.href
                }));
                return { headers, actions: firstRowLinks };
            }),
            forms: Array.from(document.querySelectorAll('form')).map(form => {
                const inputs = Array.from(form.querySelectorAll('input, select, textarea')).map(input => ({
                    name: input.name || input.id,
                    type: input.type || input.tagName.toLowerCase(),
                    label: input.closest('.form-group, label, parentNode')?.innerText?.split('\\n')[0]?.trim() || input.placeholder || ''
                })).filter(i => i.name && i.type !== 'hidden');
                return { action: form.action, method: form.method, inputs };
            })
        };
        
        // Deduplicate buttons
        const uniqueBtns = [];
        const seen = new Set();
        info.buttons.forEach(b => {
            const key = b.text + "|" + (b.href || '');
            if(!seen.has(key)) { seen.add(key); uniqueBtns.push(b); }
        });
        info.buttons = uniqueBtns;
        
        return info;
    }""")

def run():
    print("Starting Deep Scraper...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1366, 'height': 768})
        page = context.new_page()
        
        print(f"Navigating to {BASE_URL}/login...")
        try:
            page.goto(f"{BASE_URL}/login", timeout=60000)
            page.wait_for_selector("input[type='email']", timeout=10000)
            page.fill("input[type='email']", "wachiramboche@gmail.com")
            page.fill("input[type='password']", "Awesome@15")
            page.click("button[type='submit'], input[type='submit'], .btn-primary")
            print("Submitted login form.")
        except Exception as e:
            print("Failed to login:", e)
            return
            
        print("Waiting for dashboard to load...")
        try:
            page.wait_for_selector('aside, .main-sidebar, #sidebar', timeout=20000)
        except Exception:
            pass
        time.sleep(3)
        
        print("Extracting full sidebar menus...")
        tree = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('aside a, .sidebar a, .main-menu a'));
            return links.map(a => {
                const text = a.innerText.replace(/\\n/g, ' ').trim();
                let parentText = null;
                const pLi = a.closest('ul') ? a.closest('ul').closest('li') : null;
                if (pLi) {
                    const pA = pLi.querySelector('a');
                    if(pA) parentText = pA.innerText.replace(/\\n/g, ' ').trim();
                }
                return { name: text, url: a.href, parent: parentText === text ? null : parentText };
            }).filter(i => i.name && i.url && !i.url.startsWith('javascript'));
        }""")
        
        urls_to_visit = {}
        for item in tree:
            if item['url'] and 'http' in item['url'] and 'logout' not in item['url'].lower():
                path = item['url']
                if path not in urls_to_visit:
                    title = f"{item['parent']} > {item['name']}" if item['parent'] else item['name']
                    urls_to_visit[path] = title
                    
        print(f"Found {len(urls_to_visit)} unique menu URLs to analyze deeply.")
        
        site_map = {}
        
        for url, title in urls_to_visit.items():
            print(f"\\n==> Deep diving: {title} ({url})")
            try:
                page.goto(url, timeout=30000)
                page.wait_for_load_state("networkidle", timeout=10000)
                
                info = extract_page_info(page)
                
                # Check for "Add New", "Create", "Edit" buttons representing subpages or modals
                sub_actions = {}
                for btn in info['buttons']:
                    if btn['href'] and btn['href'].startswith(BASE_URL) and btn['href'] != url and '#' not in btn['href']:
                        action_name = btn['text'].lower()
                        if 'add' in action_name or 'new' in action_name or 'create' in action_name:
                            print(f"    -> Exploring Add/New sub-action: {btn['text']} ({btn['href']})")
                            try:
                                new_page = context.new_page()
                                new_page.goto(btn['href'], timeout=20000)
                                new_page.wait_for_load_state("networkidle", timeout=5000)
                                sub_info = extract_page_info(new_page)
                                sub_actions[btn['text']] = {
                                    'url': btn['href'],
                                    'info': sub_info
                                }
                                new_page.close()
                            except Exception as sub_e:
                                print(f"      [!] Failed to load sub-action: {sub_e}")
                                if 'new_page' in locals() and not new_page.is_closed():
                                    new_page.close()
                
                for table in info['tables']:
                    for action in table['actions']:
                        action_name = action['text'].lower()
                        # Often Edit buttons just have icons like "fa fa-edit", so we look for 'edit' or 'update' in URL
                        if 'edit' in action_name or 'update' in action_name or 'edit' in action['href'].lower():
                            if action['href'] and action['href'].startswith(BASE_URL) and action['href'] != url:
                                print(f"    -> Exploring Edit table action: {action['text']} ({action['href']})")
                                try:
                                    new_page = context.new_page()
                                    new_page.goto(action['href'], timeout=20000)
                                    new_page.wait_for_load_state("networkidle", timeout=5000)
                                    sub_info = extract_page_info(new_page)
                                    sub_actions['Table_Row_Edit_Template'] = {
                                        'example_url': action['href'],
                                        'info': sub_info
                                    }
                                    new_page.close()
                                    break 
                                except Exception as sub_e:
                                    print(f"      [!] Failed to load table action: {sub_e}")
                                    if 'new_page' in locals() and not new_page.is_closed():
                                        new_page.close()

                info['sub_actions'] = sub_actions
                site_map[title] = {
                    'url': url,
                    'details': info
                }
                
                with open("tolet_deep_structure.json", "w") as f:
                    json.dump(site_map, f, indent=4)
                    
            except Exception as e:
                print(f"  -> Error deep-diving {url}: {str(e)[:100]}")
                site_map[title] = {"url": url, "error": str(e)}

        print("\\nDone! Deep structure saved to 'tolet_deep_structure.json'")

if __name__ == "__main__":
    run()
