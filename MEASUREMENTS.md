# Where the article's numbers came from

Every figure in **How to scrape Google Trends with Python using ScrapingBee** that
is not linked to a source came from our own runs. This says which run, and what
you can run to get your own. Treat ours as a snapshot: Trends samples, caches and
rate-limits, so your numbers will differ.

## Check without spending anything

No key, no network. Parses the committed payloads and confirms the parser still
reads them and still refuses four kinds of damage.

```bash
python3 test_fixtures.py
```

## Measure on your own account

Each call bills. `latency` spends 6 calls, `noise` spends 2.

```bash
export SCRAPINGBEE_API_KEY="..."
python3 measure.py latency
python3 measure.py noise
```

`noise` is the one worth running before you trust a small movement. The article's
reporting-threshold advice comes from one pair of pulls on one query; yours may
sit somewhere else entirely.

## Figure by figure

### Reproducible from this repo

| Figure in the article | How |
|---|---|
| a 12-month window returns 53 or 54 weekly points | `fixtures/timeseries.json`, 53 points, trailing bucket unfinished |
| every response carries a 100 | same fixture |
| related queries return a top list and a rising list | `fixtures/related_queries.json`, 25 and 25 |
| `hasData` is on the top list and absent from the rising one | same fixture |
| rising `value` is a percentage, shown as `Breakout` past the cap | same fixture |
| the widget request names the keyword | `fixtures/widget_request_*.json` |
| `today 12-m` resolved to an absolute window | same, `time` field |

### Reproducible against your own account

| Figure | Command | Ours, 14 September 2026 |
|---|---|---|
| call latency | `python3 measure.py latency` | 4 of 6 returned, median 8.1s, max 10.6s |
| pull-to-pull variation | `python3 measure.py noise` | two pairs a week apart: 42 of 52 both times, median 2 both times, max 5 then 8 |
| credits a call | read `Spb-cost` on any response | 15 on Google domains |
| your plan's ceilings | `GET /api/v1/usage` | 100,000 credits a month, 100 concurrent |
| items the RSS feed returns | `python3 -c "import google_trends as gt; print(len(gt.trending_now('US')))"` | 10 on every request we made |

### Measured once, on our account, in August and September 2026

These came from one-off runs under conditions you cannot reproduce: a different
address, a different day, a different cache. They are reported as observations,
not as rates you should expect.

- category spreads on `python`: mean 13.1 and max 32 for Computers, mean 43.7 and max 55 for Finance
- `geo` sub-region spreads on `wildfire`: up to 42, 38 and 44 points
- `tz` across 0, -480 and 330: 6 calls, 3 distinct responses, groupings not following `tz`
- the `/trending` page: more than 500 terms, and 517 rows shared between a 24-hour and a 168-hour capture, 76 of them reporting a larger volume in the wider window
- the RSS feed's window: two pulls covered 20 minutes and 110 minutes, so the span moves with the news cycle even though the item count held at 10
- RSS parameters: `geo` was the only one that changed the body; `hours`, `category` and `hl` each returned a response byte-identical to the `geo`-only call
- `trendspyg` from one residential address: 3 of 12 keywords succeeded, cooldown over 15 minutes
- the five-query shape check: 53, 93, 53, 262 and 93 points across 4 countries and 3 timeframes

If you run any of these and get something different, that is the expected
outcome rather than a contradiction.
