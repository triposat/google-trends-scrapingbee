"""Parse the committed fixtures. A Google payload reorder fails here, not in prod.

    python3 test_fixtures.py

This is the test the article tells you to write. It makes no network calls, so
it runs in CI with no key and costs nothing.
"""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import google_trends as gt

FIX = os.path.join(HERE, "fixtures")
read = lambda n: io.open(os.path.join(FIX, n), encoding="utf-8").read()

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok    {name}")
    except Exception as exc:
        failures.append(name)
        print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")


def raises(exc_type, fn, label):
    try:
        fn()
    except exc_type:
        return
    except Exception as exc:
        raise AssertionError(f"{label}: got {type(exc).__name__}, wanted {exc_type.__name__}")
    raise AssertionError(f"{label}: nothing raised, wanted {exc_type.__name__}")


def timeseries_parses():
    series = gt.parse_timeline(read("timeseries.json"), 1)
    assert len(series) == 53, len(series)
    assert series[-1]["partial"] is True, "the trailing bucket should be unfinished"
    assert sum(1 for p in series if p["partial"]) == 1
    assert max(v for p in series for v in p["values"]) == 100
    times = [p["time"] for p in series]
    assert times == sorted(set(times)), "timestamps must be strictly ascending"


def related_parses():
    r = gt.parse_related(read("related_queries.json"), 1)
    assert len(r["top"]) == 25, len(r["top"])
    assert len(r["rising"]) == 25, len(r["rising"])
    assert r["top"][0]["value"] == 100, "the top list is normalised to 100"
    assert any(x["formatted"] == "Breakout" for x in r["rising"])


def identity_accepts_the_right_keyword():
    gt.check_identity(json.loads(read("widget_request_timeseries.json")), ["ai agents"])
    gt.check_identity(json.loads(read("widget_request_related_queries.json")), ["AI AGENTS"])


def identity_rejects_a_crossed_response():
    for f in ("widget_request_timeseries.json", "widget_request_related_queries.json"):
        raises(gt.DataQuality,
               lambda f=f: gt.check_identity(json.loads(read(f)), ["machine learning"]), f)


def identity_rejects_an_unknown_shape():
    raises(gt.SchemaChanged, lambda: gt.check_identity({"nothing": 1}, ["x"]), "unknown shape")


def parser_refuses_damage():
    good = json.loads(read("timeseries.json")[read("timeseries.json").index("{"):])
    def mangled(fn):
        d = json.loads(json.dumps(good))
        fn(d["default"]["timelineData"])
        return ")]}'\n" + json.dumps(d)
    def dupe_time(pts):   pts[5]["time"] = pts[4]["time"]
    def drop_period(pts): del pts[10]
    def out_of_range(pts): pts[3]["value"] = [101]
    def early_partial(pts): pts[2]["isPartial"] = True
    for label, fn in [("duplicate timestamp", dupe_time), ("missing period", drop_period),
                      ("value past 100", out_of_range), ("early partial", early_partial)]:
        raises(gt.SchemaChanged, lambda fn=fn: gt.parse_timeline(mangled(fn), 1), label)


for name, fn in [
    ("timeseries fixture parses", timeseries_parses),
    ("related-queries fixture parses", related_parses),
    ("identity accepts the right keyword", identity_accepts_the_right_keyword),
    ("identity rejects a crossed response", identity_rejects_a_crossed_response),
    ("identity rejects an unknown shape", identity_rejects_an_unknown_shape),
    ("parser refuses four kinds of damage", parser_refuses_damage),
]:
    check(name, fn)

print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
