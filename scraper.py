import re
import time
import json
import os
from datetime import date, datetime

from playwright.sync_api import sync_playwright

# ============================================================
#  CATEGORY MAPPINGS
# ============================================================

CATEGORIES = {
    "Fruit & Vegetables":       ("fruit-veg",            "fruit-vegetables"),
    "Meat & Seafood":           ("meat-seafood-deli",     "meat-seafood"),
    "Dairy, Eggs & Fridge":     ("dairy-eggs-fridge",     "dairy-eggs-fridge"),
    "Bakery":                   ("bakery",                "bakery"),
    "Deli":                     ("deli",                  "deli"),
    "Pantry":                   ("pantry",                "pantry"),
    "Snacks & Confectionery":   ("snacks-confectionery",  "chips-chocolates-snacks"),
    "Drinks":                   ("drinks",                "drinks"),
    "Beer, Wine & Spirits":     ("beer-wine-spirits",     "liquorland"),
    "Frozen":                   ("freezer",               "frozen"),
    "Cleaning & Laundry":       ("cleaning-maintenance",  "cleaning-laundry"),
    "Health & Beauty":          ("beauty-personal-care",  "health-beauty"),
    "Dietary & World Foods":    ("health-wellness",       "dietary-world-foods"),
    "Baby":                     ("baby",                  "baby"),
    "Pet":                      ("pet",                   "pet"),
    "Easter":                   ("easter",                "easter"),
}

COLES_PATH_OVERRIDES = {
    # e.g. "SomeCat": "offers",
}

PAGE_SIZE_WOOLWORTHS = 36
PAGE_SIZE_COLES      = 48

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

CONTEXT_OPTIONS = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "viewport":    {"width": 1280, "height": 800},
    "locale":      "en-AU",
    "timezone_id": "Australia/Sydney",
}

ANTI_BOT_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', { get: function() { return undefined; } });"
    "Object.defineProperty(navigator, 'plugins',   { get: function() { return [1,2,3]; } });"
    "Object.defineProperty(navigator, 'languages', { get: function() { return ['en-AU','en']; } });"
    "window.chrome = { runtime: {} };"
)

WOOLWORTHS_BASE = "https://www.woolworths.com.au/shop/browse/"

WOOLWORTHS_NOISE_PHRASES = [
    "ONLY AT WOOLWORTHS.",
    "Everyday low price.",
    "Boost to collect 10x points.",
]


# ============================================================
#  SHARED HELPERS
# ============================================================

def clean_woolworths_name(name):
    for phrase in WOOLWORTHS_NOISE_PHRASES:
        name = re.compile(re.escape(phrase), re.IGNORECASE).sub("", name)
    return re.sub(r"\s{2,}", " ", name).strip().strip(".")


def parse_aria_label(label):
    if not label:
        return None, None, None
    label    = label.strip().rstrip(".")
    segments = re.split(r"\s+\.\s+", label)
    parts    = [p.strip() for p in segments[-1].split(",")]
    name     = parts[0] if parts else "N/A"
    price    = parts[1].replace("$", "").strip() if len(parts) > 1 else "N/A"
    cup      = parts[2].strip()                   if len(parts) > 2 else "N/A"
    try:
        float(price)
    except (ValueError, TypeError):
        return None, None, None
    skip = ["non-member price", "range was", "get one", "bonus",
            "member price", "save $", "was $"]
    if any(s in name.lower() for s in skip):
        return None, None, None
    name = clean_woolworths_name(name)
    return (None, None, None) if not name else (name, price, cup)


def safe_filename(category):
    return (category.lower()
                    .replace(" ", "_")
                    .replace(",", "")
                    .replace("&", "and"))


# ============================================================
#  SAVE
# ============================================================

def save_category(cat, w_products, c_products, output_folder=None):
    filename = safe_filename(cat) + ".json"
    out      = os.path.join(output_folder, filename) if output_folder else filename

    if not w_products and not c_products:
        print("  No products for: " + cat + " — skipping save.")
        return

    data = {
        "category":   cat,
        "date":       date.today().isoformat(),
        "woolworths": w_products,
        "coles":      c_products,
    }

    with open(out, "w") as f:
        json.dump(data, f, indent=2)

    print("  Saved " + out + "  (W: " + str(len(w_products))
          + " / C: " + str(len(c_products)) + " products)")


# ============================================================
#  WOOLWORTHS — JavaScript snippets
# ============================================================

_JS_SCROLL_TO_BOTTOM = """() => {
    return new Promise(function(resolve) {
        var last = 0;
        var unchanged = 0;
        var timer = setInterval(function() {
            window.scrollBy(0, 700);
            var h = document.body.scrollHeight;
            if (h === last) {
                unchanged++;
                if (unchanged >= 3) { clearInterval(timer); resolve(); }
            } else {
                unchanged = 0;
            }
            last = h;
        }, 400);
    });
}"""

_JS_SHADOW = r"""(function() {
    var out = [];
    var tiles = document.querySelectorAll('shared-product-tile');
    for (var i = 0; i < tiles.length; i++) {
        var wc = tiles[i].querySelector('wc-product-tile');
        if (!wc || !wc.shadowRoot) continue;
        var sr = wc.shadowRoot;
        var links = sr.querySelectorAll('a[aria-label]');
        for (var j = 0; j < links.length; j++) {
            var a     = links[j];
            var lbl   = a.getAttribute('aria-label') || '';
            var href  = a.getAttribute('href') || '';
            var idm   = href.match(/productdetails\/([0-9]+)/);
            var sc    = idm ? idm[1] : null;
            if (!sc) continue;

            if (lbl.indexOf('$') === -1) {
                if (lbl.toLowerCase().indexOf('find out more') === -1) continue;
                var name = (a.innerText || '').trim();
                if (!name) continue;

                var price = 'N/A';
                var primEl = sr.querySelector('.product-tile-price .primary');
                if (!primEl) {
                    var promo = sr.querySelector('.label-price-promotion');
                    if (promo) primEl = promo.querySelector('.primary');
                }
                if (primEl) {
                    for (var n = 0; n < primEl.childNodes.length; n++) {
                        var nd = primEl.childNodes[n];
                        if (nd.nodeType === 3) {
                            var tv = nd.textContent.replace('$', '').trim();
                            if (tv && !isNaN(parseFloat(tv))) { price = tv; break; }
                        }
                    }
                    if (price === 'N/A') {
                        var pm = (primEl.innerText || '').match(/\$([0-9]+(?:\.[0-9]{1,2})?)/);
                        if (pm) price = pm[1];
                    }
                }
                if (price === 'N/A') continue;

                var wasp = 'N/A';
                var secEl = sr.querySelector('.product-tile-price .secondary');
                if (!secEl) {
                    var promoFb = sr.querySelector('.label-price-promotion');
                    if (promoFb) secEl = promoFb.querySelector('.secondary');
                }
                if (secEl) {
                    var sm = (secEl.innerText || '').match(/\$([0-9]+(?:\.[0-9]{1,2})?)/);
                    if (sm) wasp = sm[1];
                }

                var cup = 'N/A';
                var cups = sr.querySelector('.price-per-cup');
                if (cups) cup = (cups.innerText || '').trim();

                out.push({ bws:true, sc:sc, name:name, price:price, wasp:wasp, cup:cup });
                continue;
            }

            var wasp2 = 'N/A';
            var wbl = sr.querySelector('[aria-labelledby*="was"]');
            if (wbl && wbl.innerText) wasp2 = wbl.innerText.replace('$','').trim();
            if (wasp2 === 'N/A') {
                var wbc = sr.querySelector('[class*="was-price"]');
                if (wbc && wbc.innerText) wasp2 = wbc.innerText.replace('$','').trim();
            }
            if (wasp2 === 'N/A') {
                var all = sr.querySelectorAll('*');
                for (var k = 0; k < all.length; k++) {
                    var t = (all[k].innerText || '').trim();
                    if (/^Was \$[0-9]/.test(t)) {
                        wasp2 = t.replace('Was','').replace('$','').trim(); break;
                    }
                }
            }
            out.push({ bws:false, sc:sc, lbl:lbl, wasp:wasp2 });
        }
    }
    return out;
})()"""

_JS_HAS_NEXT = r"""(function() {
    var btns = document.querySelectorAll('a, button');
    for (var i = 0; i < btns.length; i++) {
        var t = (btns[i].getAttribute('aria-label') || btns[i].innerText || '').toLowerCase();
        if (t.indexOf('next') !== -1 && !btns[i].disabled) return true;
    }
    return false;
})()"""


def get_woolworths_total_pages(page):
    try:
        txt = page.inner_text(
            "wc-pagination, .pagination, [class*='pagination'], wx-pagination",
            timeout=5000)
        m = re.search(r"[Pp]age\s+\d+\s+of\s+(\d+)", txt)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def scroll_woolworths_page(page):
    try:
        page.evaluate(_JS_SCROLL_TO_BOTTOM)
        time.sleep(0.5)
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
    except Exception as e:
        print("    Warning: scroll failed: " + str(e)[:60])


def scrape_woolworths_category(page, category_name, slug):
    all_products = []
    current_page = 1
    seen         = set()
    total_pages  = None

    print("  [Woolworths] " + category_name + " (/shop/browse/" + slug + ")")

    while True:
        url = WOOLWORTHS_BASE + slug
        if current_page > 1:
            url += "?pageNumber=" + str(current_page)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print("    Page load error p" + str(current_page) + ": " + str(e)[:80])
            current_page += 1
            time.sleep(3)
            continue

        try:
            page.wait_for_selector("shared-product-tile", timeout=15000)
        except Exception:
            print("    No product tiles on page " + str(current_page) + ". Stopping.")
            break

        if current_page == 1:
            try:
                page.locator(".chip-text", has_text="Hide Everyday Market").first.click(timeout=5000)
                print("    Applied Hide Everyday Market filter")
                time.sleep(3)
                page.wait_for_selector("shared-product-tile", timeout=15000)
            except Exception:
                pass
            total_pages = get_woolworths_total_pages(page)
            print("    " + (str(total_pages) + " pages to capture"
                            if total_pages else "Page count unavailable"))

        time.sleep(2)
        print("    Scrolling page to render all tiles...")
        scroll_woolworths_page(page)

        time.sleep(1)
        raw = page.evaluate(_JS_SHADOW)

        if not raw:
            print("    No products — waiting 15s and retrying...")
            time.sleep(15)
            scroll_woolworths_page(page)
            raw = page.evaluate(_JS_SHADOW)

        if not raw:
            print("    No products extracted. Stopping.")
            break

        new_count = 0
        for item in raw:
            sc = item["sc"]
            if sc in seen:
                continue
            seen.add(sc)

            if item["bws"]:
                name = clean_woolworths_name(item["name"])
                if not name:
                    continue
                all_products.append({
                    "Category":    category_name,
                    "Name + Size": name,
                    "Price":       item["price"],
                    "WasPrice":    item["wasp"],
                    "CupPrice":    item["cup"],
                    "PackageSize": "N/A",
                    "Stockcode":   sc,
                    "IsOnSpecial": item["wasp"] != "N/A",
                    "Brand":       "N/A",
                })
            else:
                name, price, cup = parse_aria_label(item["lbl"])
                if not name:
                    continue
                all_products.append({
                    "Category":    category_name,
                    "Name + Size": name,
                    "Price":       price,
                    "WasPrice":    item["wasp"],
                    "CupPrice":    cup,
                    "PackageSize": "N/A",
                    "Stockcode":   sc,
                    "IsOnSpecial": item["wasp"] != "N/A",
                    "Brand":       "N/A",
                })
            new_count += 1

        pg = (str(current_page) + "/" + str(total_pages)) if total_pages else str(current_page)
        print("    Page " + pg + ": got " + str(new_count)
              + " new (total: " + str(len(all_products)) + ")")

        if new_count == 0:
            print("    No new products. Done.")
            break

        if not page.evaluate(_JS_HAS_NEXT):
            print("    No more pages.")
            break

        current_page += 1
        time.sleep(2)

    print("    Done: " + str(len(all_products)) + " products")
    return all_products


# ============================================================
#  COLES
# ============================================================

def wait_for_captcha_clear(page, context=""):
    try:
        html = page.content()
    except Exception:
        return False
    if "hcaptcha" not in html.lower() and "additional security check" not in html.lower():
        return False
    print("  !! CAPTCHA DETECTED" + (" (" + context + ")" if context else "") + " — skipping.")
    return True


def get_coles_build_id(page):
    html = page.content()
    for pat in [r'"buildId"\s*:\s*"([^"]+)"',
                r'/_next/static/([^/\'"]+)/_buildManifest']:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def fetch_fresh_build_id(page):
    print("  Refreshing Coles build ID...")
    for _ in range(3):
        try:
            page.goto("https://www.coles.com.au",
                      wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        time.sleep(2)
        if wait_for_captcha_clear(page, "homepage"):
            continue
        bid = get_coles_build_id(page)
        if bid:
            print("  Build ID: " + bid)
            return bid
    print("  WARNING: Could not obtain build ID.")
    return None


def fetch_coles_json(page, build_id, slug, page_num, path_prefix="browse"):
    url = ("https://www.coles.com.au/_next/data/"
           + build_id + "/en/" + path_prefix + "/" + slug + ".json"
           + "?slug=" + slug
           + ("&page=" + str(page_num) if page_num > 1 else ""))
    for _ in range(3):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("    Nav error p" + str(page_num) + ": " + str(e))
            return None
        if wait_for_captcha_clear(page, slug + " p" + str(page_num)):
            continue
        try:
            return json.loads(page.inner_text("body"))
        except Exception as e:
            print("    JSON parse error p" + str(page_num) + ": " + str(e))
            return None
    return None


def extract_coles_products(data, category):
    products   = []
    pp         = data.get("pageProps", {})
    results    = pp.get("searchResults", {}).get("results", [])
    if not results:
        results = pp.get("catalogueData", {}).get("results", [])
    for item in results:
        pricing   = item.get("pricing", {}) or {}
        name      = item.get("name", "N/A")
        if not name or name == "N/A" or not str(name).strip():
            continue
        brand     = item.get("brand", "") or ""
        full_name = (brand.strip() + " " + name.strip()).strip()
        size      = str(item.get("size") or "").strip()
        name_size = (full_name + " " + size).strip() if size and size != "N/A" else full_name
        products.append({
            "Category":    category,
            "Name + Size": name_size,
            "Full Name":   full_name,
            "Name":        name,
            "Price":       pricing.get("now",        "N/A"),
            "WasPrice":    pricing.get("was",        "N/A"),
            "CupPrice":    pricing.get("comparable", "N/A"),
            "PackageSize": size or "N/A",
            "Stockcode":   item.get("id",            "N/A"),
            "IsOnSpecial": pricing.get("onSpecial",  False),
            "Brand":       brand,
        })
    return products


def get_coles_total_and_pages(data):
    if not data:
        return 0, 0
    pp    = data.get("pageProps", {})
    total = pp.get("searchResults", {}).get("noOfResults", 0)
    if not total:
        total = pp.get("catalogueData", {}).get("noOfResults", 0)
    return total, (-(-total // PAGE_SIZE_COLES) if total else 0)


def scrape_coles_category(page, build_id, category_name, slug, path_prefix="browse"):
    all_products = []
    print("  [Coles] " + category_name + " (/" + path_prefix + "/" + slug + ")")

    data = fetch_coles_json(page, build_id, slug, 1, path_prefix)
    if not data:
        print("    Could not fetch page 1. Skipping.")
        return []

    total, total_pages = get_coles_total_and_pages(data)
    products           = extract_coles_products(data, category_name)
    if total == 0 and not products:
        print("    No products found. Skipping.")
        return []

    print("    " + str(total) + " products across " + str(total_pages) + " pages")
    all_products.extend(products)
    print("    Page 1/" + str(total_pages) + ": got " + str(len(products))
          + " (total: " + str(len(all_products)) + ")")

    for pn in range(2, total_pages + 1):
        data = fetch_coles_json(page, build_id, slug, pn, path_prefix)
        if not data:
            print("    No data on page " + str(pn) + ". Stopping.")
            break
        products = extract_coles_products(data, category_name)
        if not products:
            print("    Empty page " + str(pn) + ". Stopping.")
            break
        all_products.extend(products)
        print("    Page " + str(pn) + "/" + str(total_pages)
              + ": got " + str(len(products))
              + " (total: " + str(len(all_products)) + ")")
        if len(products) < PAGE_SIZE_COLES:
            print("    Short page - reached end.")
            break
        time.sleep(1)

    print("    Done: " + str(len(all_products)) + " products")
    return all_products


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    start_time    = datetime.now()
    cat_list      = list(CATEGORIES.keys())
    selected      = [(cat, "BOTH") for cat in cat_list]
    output_folder = os.path.join("data", date.today().strftime("%Y-%m-%d"))

    print("=" * 55)
    print("   Supermarket Category Scraper")
    print("   Woolworths + Coles — all " + str(len(selected)) + " categories")
    print("   Output: " + output_folder)
    print("=" * 55)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    with sync_playwright() as p:

        print("Opening Coles browser...")
        coles_browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        coles_ctx     = coles_browser.new_context(**CONTEXT_OPTIONS)
        coles_ctx.add_init_script(ANTI_BOT_SCRIPT)
        coles_page    = coles_ctx.new_page()

        print("Opening Woolworths browser...")
        wool_browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        wool_ctx     = wool_browser.new_context(**CONTEXT_OPTIONS)
        wool_ctx.add_init_script(ANTI_BOT_SCRIPT)
        wool_page    = wool_ctx.new_page()

        def block_resources(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                route.abort()
            else:
                route.continue_()

        wool_page.route("**/*", block_resources)

        print("Loading Woolworths homepage...")
        try:
            wool_page.goto("https://www.woolworths.com.au",
                           wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        time.sleep(3)

        try:
            for idx, (cat, store) in enumerate(selected, 1):
                print()
                print("=" * 55)
                print("  CATEGORY " + str(idx) + "/" + str(len(selected)) + ": " + cat)
                print("=" * 55)

                c_slug        = CATEGORIES[cat][1]
                w_slug        = CATEGORIES[cat][0]
                c_path_prefix = COLES_PATH_OVERRIDES.get(cat, "browse")

                print()
                bid = fetch_fresh_build_id(coles_page)
                c_products = []
                if bid:
                    c_products = scrape_coles_category(
                        coles_page, bid, cat, c_slug, c_path_prefix)
                else:
                    print("  Could not get Coles build ID — skipping Coles for " + cat)

                print()
                w_products = scrape_woolworths_category(wool_page, cat, w_slug)

                print()
                print("  Saving " + cat + "...")
                save_category(cat, w_products, c_products, output_folder)
                time.sleep(2)

        except KeyboardInterrupt:
            print()
            print("  Interrupted — last completed category already saved.")

        finally:
            for browser in (coles_browser, wool_browser):
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass

    elapsed   = datetime.now() - start_time
    total_sec = int(elapsed.total_seconds())
    hours     = total_sec // 3600
    minutes   = (total_sec % 3600) // 60
    seconds   = total_sec % 60

    print()
    print("=" * 55)
    if hours > 0:
        print("  Total time: " + str(hours) + "h " + str(minutes) + "m " + str(seconds) + "s")
    else:
        print("  Total time: " + str(minutes) + "m " + str(seconds) + "s")
    print("  All done!")
    print("=" * 55)
