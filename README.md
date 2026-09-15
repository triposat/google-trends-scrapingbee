# Google Trends scraper: runnable script and fixtures

Companion artifacts for **How to scrape Google Trends with Python using ScrapingBee**.

| File | What it is |
|---|---|
| `google_trends.py` | Every class, function and constant printed in the article, in one importable module. Generated, never hand-edited. |
| `build.py` | Regenerates `google_trends.py` from the article's code blocks. `--check` fails if the two have drifted. |
| `test_fixtures.py` | Parses the committed fixtures. No network, no API key, no cost. |
| `measure.py` | Re-measures call latency and pull-to-pull variation on your own account. |
| `MEASUREMENTS.md` | Where every figure in the article came from, and what to run to get your own. |
| `fixtures/timeseries.json` | One real `/widgetdata/multiline` payload, 53 weekly points, trailing bucket unfinished. |
| `fixtures/related_queries.json` | One real `/widgetdata/relatedsearches` payload, 25 top and 25 rising. |
| `fixtures/widget_request_*.json` | The two widget requests, which carry the keyword and the window Google resolved the timeframe to. |

Captured 14 September 2026. They contain public Trends responses only: no key, no
token, no cookie.

## Use

```bash
pip install requests
export SCRAPINGBEE_API_KEY="your_key_here"
python3 -c "import google_trends as gt; print(gt.trending_now('US')[:3])"
```

## Keep it honest

```bash
python3 test_fixtures.py   # the parser still reads a known-good payload
```

Run it in CI. It catches Google reordering a payload: the parse fails in the test
rather than writing wrong rows into your database.

`build.py` regenerates `google_trends.py` from the article's markdown, so the code
here cannot drift from the code on the page. It needs that markdown, which lives
with the article rather than in this repo, so it is a maintainer's tool:
`TRENDS_ARTICLE=/path/to/article.md python3 build.py --check`.
