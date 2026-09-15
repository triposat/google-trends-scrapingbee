"""Google Trends via the ScrapingBee HTML API.

Generated from the code blocks of the published article, so the two cannot
drift. The article's maintainer regenerates it with build.py in this repo.

Article:  How to scrape Google Trends with Python using ScrapingBee
Version:  2026-09-14
Requires: requests
Set SCRAPINGBEE_API_KEY in the environment before calling anything here.
"""

import json, os, time, requests


class TrendsError(Exception):
    """Base class, so callers can catch everything this module raises."""


class RetryableRequest(TrendsError):
    """A throttle from either side, a 5xx, a render that never finished, or a
    request that never reached ScrapingBee. Raised once the attempts inside the
    call run out, so a job wrapper knows this one is worth another go."""


class SchemaChanged(TrendsError):
    """A response arrived, but not in the shape this parser reads."""


class RequestRejected(TrendsError):
    """The request itself was refused. Repeating it changes nothing."""


class DataQuality(TrendsError):
    """The response parsed, but it can't answer what was asked."""


# The classic Explore endpoint compares up to 5 terms in one call, the cap when
# we tested, September 2026. If a longer list stops returning HTTP 400, raise it:
# Google's Explore help page carries the current figure.
MAX_COMPARISON_ITEMS = 5


CHAIN = """
window.__out = 'PENDING';
window.__req = '';

// Plant a marker the scenario can wait on, so the request returns the moment
// the payload lands instead of after a fixed wait.
function done() {
  var d = document.createElement('div');
  d.id = 'trends-done';
  document.body.appendChild(d);
}

var req = JSON.stringify({comparisonItem: %s, category: %s, property: ''});
fetch('/trends/api/explore?hl=en-US&tz=0&req=' + encodeURIComponent(req),
      {credentials: 'include'})
  .then(function (r) {
    // Surface the status before parsing. A bad geo or a sixth keyword comes
    // back as an error page, and JSON.parse would report that as a syntax
    // error rather than as the rejected request it is.
    if (r.status !== 200) { window.__out = 'HTTP_' + r.status; done(); return null; }
    return r.text();
  })
  .then(function (t) {
    if (t === null) { return; }
    var explore = JSON.parse(t.substring(t.indexOf('{')));
    var widget = explore.widgets.filter(function (w) {
      return w.id === 'TIMESERIES';
    })[0];
    // The data payload carries no keyword. This does, along with the absolute
    // window Google resolved the timeframe to. Keep it for the identity check.
    window.__req = JSON.stringify(widget.request);
    var url = '/trends/api/widgetdata/multiline?hl=en-US&tz=0'
            + '&req=' + encodeURIComponent(JSON.stringify(widget.request))
            + '&token=' + encodeURIComponent(widget.token);
    return fetch(url, {credentials: 'include'}).then(function (r2) {
      return r2.text().then(function (body) {
        window.__out = r2.status === 200 ? body : 'HTTP_' + r2.status;
        done();
      });
    });
  })
  .catch(function (e) { window.__out = 'ERROR::' + e; done(); });
'started'
"""


def parse_timeline(raw, keyword_count):
    """Turn Google's payload into rows, or say exactly what stopped the parse."""
    try:
        timeline = json.loads(raw[raw.index("{"):])["default"]["timelineData"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SchemaChanged(f"timelineData missing or unreadable: {exc}") from exc
    if not isinstance(timeline, list):
        raise SchemaChanged(f"timelineData is {type(timeline).__name__}, not a list")

    series = []
    for point in timeline:
        try:
            # 'time' is Google's epoch for the bucket start. Keep it: it is the
            # only safe key for joining two pulls. formattedAxisTime is display
            # text and changes with locale.
            row = {"time": int(point["time"]),
                   "date": point["formattedAxisTime"],
                   "values": list(point["value"]),
                   "partial": bool(point.get("isPartial", False))}
        except (KeyError, TypeError, ValueError) as exc:
            raise SchemaChanged(f"unexpected point shape: {point!r}") from exc
        if len(row["values"]) != keyword_count:
            raise SchemaChanged(
                f"expected {keyword_count} values a point, got {len(row['values'])}")
        if not all(isinstance(v, int) and 0 <= v <= 100 for v in row["values"]):
            raise SchemaChanged(f"values outside the 0-100 scale: {row['values']}")
        series.append(row)

    if not series:
        raise SchemaChanged("timelineData was empty")
    times = [p["time"] for p in series]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise SchemaChanged("points are not in strictly ascending time order")
    # Granularity: Google's buckets are evenly spaced for a given timeframe.
    # Month lengths vary by about 11%, so allow slack; a dropped period doubles
    # a gap and is caught here rather than becoming a silent hole in the series.
    gaps = [b["time"] - a["time"] for a, b in zip(series, series[1:])]
    if gaps and max(gaps) > 1.5 * min(gaps):
        raise SchemaChanged(f"uneven buckets, {min(gaps)}s to {max(gaps)}s: "
                            "a period is missing")
    if any(p["partial"] for p in series[:-1]):
        raise SchemaChanged("a partial point appeared before the end of the series")

    # At least one value in the whole response is 100, on whichever keyword and
    # week is busiest. It is not always the first keyword, and a tie means more
    # than one point can hold it. An all-zero series is the exception: a term
    # below Google's threshold has no 100 to find.
    everything = [v for p in series for v in p["values"]]
    if any(everything) and max(everything) != 100:
        raise DataQuality("response has no 100; the parse or the request is wrong")
    return series


def check_identity(request, keywords):
    """Confirm the widget Google answered describes the query you asked for.

    Nothing in the data payload names a keyword, so a crossed or stale response
    parses cleanly and passes every check above. The widget request does name
    one, in a different place per widget: a `comparisonItem` list on the
    timeseries, a single `restriction` object on related queries."""
    scope = request.get("comparisonItem") or [request.get("restriction") or {}]
    try:
        answered = [k["value"] for part in scope
                    for k in part["complexKeywordsRestriction"]["keyword"]]
    except (KeyError, TypeError) as exc:
        raise SchemaChanged(f"widget request named no keyword: {exc}") from exc
    if [k.casefold() for k in answered] != [k.casefold() for k in keywords]:
        raise DataQuality(f"asked for {keywords}, the widget answered {answered}")


def fetch_widget(chain, items, category=0, retries=2):
    """Run one in-page chain. Returns Google's raw payload and the widget request
    it answered with, which `check_identity` reads to confirm the keyword. Both
    pulls come through here, so the retry, billing and status rules live in one
    place instead of two."""
    scenario = {"instructions": [
        {"wait": 2000},
        {"evaluate": chain % (json.dumps(items), json.dumps(category))},
        {"wait_for": "#trends-done"},
        {"evaluate": "window.__req"},
        {"evaluate": "window.__out"},
    ]}

    last, log = "", []
    for attempt in range(retries + 1):
        try:
            response = requests.get("https://app.scrapingbee.com/api/v1/", params={
                "api_key": os.environ["SCRAPINGBEE_API_KEY"],
                # Any Trends page can host the scenario. The geo that selects the
                # data is the one inside comparisonItem, not this URL.
                "url": "https://trends.google.com/trending?geo=US",
                "custom_google": "true",
                "render_js": "true",
                "block_resources": "false",
                "json_response": "true",
                "js_scenario": json.dumps(scenario),
            }, timeout=180)
        except requests.RequestException as exc:
            # A timeout, a reset or a DNS failure never reached ScrapingBee, so
            # there is no status to sort and nothing was billed. It has to raise
            # the same type as a throttle, or a caller's retry never sees it.
            last = f"the request never completed: {exc}"
            log.append({"request_id": "", "status": "transport", "cost": "0"})
            if attempt < retries:
                time.sleep(5)
            continue

        request_id = response.headers.get("Spb-request-id", "")
        # Read what this attempt billed rather than inferring it from the status.
        cost = response.headers.get("Spb-cost", "?")
        entry = {"request_id": request_id, "status": response.status_code,
                 "cost": cost}
        if response.status_code != 200:
            # A throttle page and a quota page carry the same status line and
            # differ in the first line of text, so keep a slice of it.
            entry["body"] = response.text[:120]
        log.append(entry)
        # Sort the failures: a 4xx is the same every time and raises now, a
        # throttle or a half-finished render is worth another attempt.
        if response.status_code == 429:
            last = f"429 from ScrapingBee, request {request_id}"
            if attempt < retries:
                time.sleep(15)
            continue
        if 400 <= response.status_code < 500:
            # A bad key or a malformed request fails the same way every time.
            raise RequestRejected(f"HTTP {response.status_code} from ScrapingBee, "
                                  f"request {request_id}. Check the key and the parameters")
        if response.status_code != 200:
            last = f"HTTP {response.status_code}, request {request_id}"
            if attempt < retries:
                time.sleep(5)
            continue

        try:
            results = response.json().get("evaluate_results") or []
        except ValueError as exc:
            raise SchemaChanged(f"non-JSON body, request {request_id}") from exc

        raw = str(results[-1]) if results else ""
        if raw.startswith(")]}"):
            # The step before the payload is window.__req.
            meta = results[-2] if len(results) > 1 else ""
            return raw, json.loads(meta or "{}")
        if raw.startswith("ERROR::"):
            # The chain threw inside the page, which is what a renamed widget or
            # a changed payload looks like. Keep the message: it names the step.
            raise SchemaChanged(f"the in-page chain failed, request {request_id}: "
                                f"{raw[7:200]}")
        if raw.startswith("HTTP_"):
            code = raw[5:]
            if code.startswith("4") and code != "429":
                # A 4xx means the request itself is wrong, usually a bad geo or a
                # keyword past the comparison cap. Retrying buys the same answer.
                raise RequestRejected(f"Google rejected the request with {raw}, "
                                      f"request {request_id}")
            last = f"Google returned {raw}, request {request_id}"
            if attempt < retries:
                time.sleep(5)
            continue
        last = f"scenario ended before the payload, request {request_id}"
        if attempt < retries:
            time.sleep(2)

    # Only the transient paths reach here: a permanent failure raised inside
    # the loop. So this is worth another attempt at the job level.
    raise RetryableRequest(f"no payload for {[i['keyword'] for i in items]} after "
                           f"{retries + 1} attempts. {last}. Billed: {log}")


def interest_over_time(keywords, geo="US", timeframe="today 12-m",
                       retries=2, category=0):
    if isinstance(keywords, str):
        keywords = [keywords]
    if not 1 <= len(keywords) <= MAX_COMPARISON_ITEMS:
        # Google refuses this too, with an HTTP 400. Raise the same type here so a
        # caller handles the local check and the remote one the same way.
        raise RequestRejected(f"the classic Explore endpoint took 1 to "
                              f"{MAX_COMPARISON_ITEMS} keywords when this was written; "
                              "check Google's Explore help page for the current cap")
    items = [{"keyword": k, "geo": geo, "time": timeframe} for k in keywords]
    raw, request = fetch_widget(CHAIN, items, category, retries)
    check_identity(request, keywords)
    return parse_timeline(raw, len(keywords))


import time


def collect(keywords, geo="US", rounds=3):
    """Retry only what a retry can fix. Everything else stops the run."""
    out, throttled = {}, []
    for keyword in keywords:
        for attempt in range(rounds):
            try:
                series = interest_over_time(keyword, geo=geo)
                # Drop the unfinished period here too. A scheduled job that
                # skipped this would persist the bucket the demo throws away.
                out[keyword] = [p for p in series if not p["partial"]]
                break
            except RetryableRequest:
                time.sleep(30 * (attempt + 1))     # back off, then try again
        else:
            throttled.append(keyword)              # still throttled after `rounds`
    return out, throttled


import os, requests


import xml.etree.ElementTree as ET


from email.utils import parsedate_to_datetime


NS = {"ht": "https://trends.google.com/trending/rss"}


def as_datetime(raw):
    """RSS dates are RFC 822. Parse them here so callers get a real datetime."""
    if not raw:
        raise SchemaChanged("an item arrived with no pubDate")
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError) as exc:
        raise SchemaChanged(f"unparseable pubDate: {raw!r}") from exc


def trending_now(geo="US"):
    try:
        response = requests.get("https://app.scrapingbee.com/api/v1/", params={
            "api_key": os.environ["SCRAPINGBEE_API_KEY"],
            "url": f"https://trends.google.com/trending/rss?geo={geo}",
            "custom_google": "true",
            "render_js": "false",
        }, timeout=120)
    except requests.RequestException as exc:
        # No response means no status to sort. Raise the retryable type so a
        # caller sees a TrendsError rather than a bare requests exception.
        raise RetryableRequest(f"the request never completed: {exc}") from exc
    if response.status_code == 429:
        raise RetryableRequest(f"429 from ScrapingBee, request "
                               f"{response.headers.get('Spb-request-id', '')}")
    if 400 <= response.status_code < 500:
        raise RequestRejected(f"HTTP {response.status_code} from the feed, request "
                              f"{response.headers.get('Spb-request-id', '')}")
    if response.status_code != 200:
        raise RetryableRequest(f"HTTP {response.status_code} from the feed, request "
                               f"{response.headers.get('Spb-request-id', '')}")

    # Both cases stop here rather than returning an empty list: an error page is
    # still valid XML sometimes, and an HTML block page is not XML at all.
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise SchemaChanged(
            f"feed did not parse as XML, request "
            f"{response.headers.get('Spb-request-id', '')}: {response.text[:120]!r}"
        ) from exc

    items = root.findall("./channel/item")
    if not items:
        raise SchemaChanged("feed parsed but carried no <item> elements")

    stories = []
    for item in items:
        title = item.findtext("title")
        if not title:
            raise SchemaChanged("an item arrived with no title")
        stories.append({
            "title": title.strip(),
            "traffic": (item.findtext("ht:approx_traffic", namespaces=NS) or "").strip(),
            "published": as_datetime(item.findtext("pubDate")),
            "news": [t.text.strip() for t in
                     item.findall("ht:news_item/ht:news_item_title", namespaces=NS)
                     if t.text],
        })
    return stories


RELATED_CHAIN = (CHAIN.replace("'TIMESERIES'", "'RELATED_QUERIES'")
                      .replace("/trends/api/widgetdata/multiline",
                               "/trends/api/widgetdata/relatedsearches"))


def parse_related(raw, keyword_count):
    """Turn the relatedsearches payload into a top list and a rising list."""
    try:
        ranked = json.loads(raw[raw.index("{"):])["default"]["rankedList"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SchemaChanged(f"rankedList missing or unreadable: {exc}") from exc
    if not isinstance(ranked, list):
        raise SchemaChanged(f"rankedList is {type(ranked).__name__}, not a list")
    # One top list and one rising list per keyword, in that order. How many
    # entries land inside each is not fixed, so check the blocks, not the rows.
    if len(ranked) != 2 * keyword_count:
        raise SchemaChanged(f"expected {2 * keyword_count} ranked lists, "
                            f"got {len(ranked)}")

    lists = []
    for block in ranked:
        rows = []
        for entry in block.get("rankedKeyword") or []:
            try:
                # Don't read `hasData`: it is on the top list and absent from
                # the rising one. `value` carries two scales under one name, a
                # 0-100 rank on the top list and a percentage rise on the
                # rising one, which `formatted` shows as "Breakout" past the
                # point where Google stops printing a number.
                rows.append({"query": str(entry["query"]),
                             "value": int(entry["value"]),
                             "formatted": str(entry["formattedValue"])})
            except (KeyError, TypeError, ValueError) as exc:
                raise SchemaChanged(f"unexpected entry shape: {entry!r}") from exc
        lists.append(rows)
    if not any(lists):
        raise DataQuality("both ranked lists came back empty")
    return {"top": lists[0], "rising": lists[1]}


def related_queries(keyword, geo="US", timeframe="today 12-m",
                    retries=2, category=0):
    """Top and rising queries for one keyword, at the cost of one call."""
    items = [{"keyword": keyword, "geo": geo, "time": timeframe}]
    raw, request = fetch_widget(RELATED_CHAIN, items, category, retries)
    check_identity(request, [keyword])
    return parse_related(raw, 1)
