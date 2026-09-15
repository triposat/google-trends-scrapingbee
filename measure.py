"""Measure on your own account what the article measured on ours.

    export SCRAPINGBEE_API_KEY="..."
    python3 measure.py latency    # call time, and how many Google refuses
    python3 measure.py noise      # how much two pulls of one query disagree

Each call bills. `latency` spends 6, `noise` spends 2.
"""
import os, sys, time, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_trends as gt

SPACING = 45          # Google refuses back-to-back calls; give it room


def latency(keywords=("ai agents", "machine learning", "python",
                      "coffee", "bitcoin", "cricket")):
    times, refused = [], 0
    for i, kw in enumerate(keywords):
        if i:
            time.sleep(SPACING)
        t0 = time.time()
        try:
            series = gt.interest_over_time(kw, geo="US", retries=0)
            dt = time.time() - t0
            times.append(dt)
            print(f"  {kw:<18} {dt:6.1f}s   {len(series)} points", flush=True)
        except gt.TrendsError as exc:
            refused += 1
            print(f"  {kw:<18}  refused  {type(exc).__name__}", flush=True)
    if times:
        print(f"\n  {len(times)} of {len(keywords)} returned data")
        print(f"  median {st.median(times):.1f}s, min {min(times):.1f}s, "
              f"max {max(times):.1f}s")
    print(f"  refused on a single attempt: {refused} of {len(keywords)}")


def noise(keyword="ai agents"):
    """Two pulls of one query, back to back. The article's own figures came
    from exactly this, so run it before you set a reporting threshold."""
    runs = []
    for i in range(2):
        if i:
            time.sleep(SPACING)
        runs.append([p for p in gt.interest_over_time(keyword, geo="US")
                     if not p["partial"]])
    a, b = runs
    n = min(len(a), len(b))
    deltas = [abs(a[i]["values"][0] - b[i]["values"][0]) for i in range(n)]
    moved = [d for d in deltas if d]
    print(f"  {len(moved)} of {n} points differ between two pulls")
    if moved:
        print(f"  median {st.median(moved):.1f}, max {max(moved)}")
        print(f"  a movement at or under {max(moved)} points is inside your own "
              f"pull-to-pull variation")
    else:
        print("  identical; your account may be served from one cache")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "latency"
    {"latency": latency, "noise": noise}[which]()
