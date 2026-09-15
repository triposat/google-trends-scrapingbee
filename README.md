# Google Trends scraper: runnable module and fixtures
| File | What it is |
|---|---|
| `google_trends.py` | Every class, function and constant printed in the article, in one importable module. Generated, never hand-edited. |
| `test_fixtures.py` | Parses the committed fixtures. No network, no API key, no cost. |
| `measure.py` | Re-measures call latency and pull-to-pull variation on your own account. **Spends credits.** |
| `MEASUREMENTS.md` | Where each figure in the article came from, and what to run to get your own. |
| `fixtures/` | Real Google responses captured 14 September 2026: one timeseries payload, one related-queries payload, and the two widget requests behind them. Public Trends data only, with no key, token or cookie in any of them. |

Python 3.8 or newer. The only dependency is `requests`.

## Start here, and spend nothing

```bash
pip install -r requirements.txt
python3 test_fixtures.py
```

That parses the committed payloads and confirms the parser still reads them, and
still refuses four kinds of damaged response. No network, no key.

Worth running in CI. When Google reorders a payload the parse fails in the test,
rather than quietly writing wrong rows wherever you store results.

## Make a live call

Calls to Google domains bill [15 credits each](https://www.scrapingbee.com/#pricing), so this step costs money.
[Sign up](https://app.scrapingbee.com/account/register) for a key, then:

```bash
export SCRAPINGBEE_API_KEY="your_key_here"
python3 -c "import google_trends as gt; print(gt.trending_now('US')[:3])"
```

`trending_now()` is the cheapest place to start: one call, and no browser render.
`interest_over_time()` and `related_queries()` each render a page, and the article
explains what that buys.
