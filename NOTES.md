# Supermarket Price Scraper — Project Brief
**Date:** 26-27 March 2026 | **Repo:** github.com/gcooke42/supermarket-prices

---

## What We're Building
A daily automated scraper that collects product prices from Woolworths and Coles across 16 categories, stores the data as JSON files in a GitHub repo.

## Original Script
- Python script using **Playwright** (browser automation) for Woolworths and **Next.js API calls** for Coles
- Scrapes 16 categories: Fruit & Veg, Meat & Seafood, Dairy, Bakery, Deli, Pantry, Snacks, Drinks, Beer/Wine/Spirits, Frozen, Cleaning, Health & Beauty, Dietary & World Foods, Baby, Pet, Easter
- Originally ran locally, interactive menu to select categories, saved to Excel
- Original script: https://gist.github.com/gcooke42/1b7b15046af5846b8641bbc653522e01

## What We Built
Modified the script and created a GitHub repo with a GitHub Actions workflow. Changes made to the script:

| Change | Reason |
|--------|--------|
| `headless=True` | GitHub Actions has no display |
| Removed `input()` menu | Hardcoded to scrape all 16 categories |
| Output changed from `.xlsx` to `.json` | Simpler for GitHub storage |
| CAPTCHA handling: log & skip | Can't do manual intervention in CI |
| Output path changed to `data/YYYY-MM-DD/` | One folder per day |

## What Failed & Why
Ran the GitHub Actions workflow manually — zero data produced.

**Root cause: IP blocking.** GitHub Actions runs on Microsoft Azure datacenter IPs. Both Woolworths and Coles detect and block these. Errors seen:
- Coles: `JSON parse error p1: Expecting value: line 1 column 1 (char 0)` — blocked page returned instead of JSON
- Woolworths: `No product tiles on page 1` — page loaded but no products rendered

## Agreed Solution: Run Locally on Windows
Use **Windows Task Scheduler** on a local machine to run the script nightly. The home/office IP won't be blocked. After scraping, the script pushes JSON data to GitHub automatically.

## What Needs To Be Done Next (Monday)
1. Confirm Python and Git are installed on the Windows machine
2. Clone the repo locally: `git clone https://github.com/gcooke42/supermarket-prices.git`
3. Install dependencies: `pip install playwright pandas openpyxl && playwright install chromium`
4. Modify the script slightly for local Windows use:
   - Switch back to `headless=False` (optional — visible browser is less likely to be blocked)
   - Add `git add / git commit / git push` at the end of the script
5. Set up Windows Task Scheduler to run the script nightly
6. Test a manual run

## Repo Structure
```
supermarket-prices/
  scraper.py               ← modified script (currently set up for GitHub Actions)
  requirements.txt
  .github/
    workflows/
      scrape.yml           ← daily workflow (currently failing due to IP block)
  data/
    YYYY-MM-DD/
      fruit_and_vegetables.json
      meat_and_seafood.json
      ... (16 files per day)
```

## Data Format (each JSON file)
```json
{
  "category": "Pantry",
  "date": "2026-03-26",
  "woolworths": [
    { "Name + Size": "...", "Price": "1.50", "WasPrice": "N/A", "CupPrice": "...", "Stockcode": "...", "IsOnSpecial": false, "Brand": "..." }
  ],
  "coles": [
    { "Name + Size": "...", "Price": "1.40", "WasPrice": "N/A", "CupPrice": "...", "Stockcode": "...", "IsOnSpecial": false, "Brand": "..." }
  ]
}
```

## Key Links
- Repo: https://github.com/gcooke42/supermarket-prices
- Actions log: https://github.com/gcooke42/supermarket-prices/actions
- Original script gist: https://gist.github.com/gcooke42/1b7b15046af5846b8641bbc653522e01
