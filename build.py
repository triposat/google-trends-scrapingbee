"""Regenerate google_trends.py from the article's own code blocks.

Keeps every class, function and CONSTANT defined in the article and drops the
demo calls. Structural, via the AST, so it cannot silently eat a loop body.

    python3 build.py          write the file
    python3 build.py --check  exit 1 if the file is out of date

Needs the article's markdown, which is not in this repo. Point at it with
TRENDS_ARTICLE=/path/to/article.md. Only the article's maintainer runs this;
everyone else runs test_fixtures.py, which needs nothing external.
"""
import ast, io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.environ.get("TRENDS_ARTICLE",
                    os.path.join(HERE, "..", "article.md"))
OUT = os.path.join(HERE, "google_trends.py")

def article_version(src):
    """Take the version from the article's own dateModified, so it cannot drift."""
    m = re.search(r'^dateModified:\s*"([\d-]+)"', src, re.M)
    return m.group(1) if m else "unknown"


HEADER = '''"""Google Trends via the ScrapingBee HTML API.

Generated from the code blocks of the published article, so the two cannot
drift. The article's maintainer regenerates it with build.py in this repo.

Article:  How to scrape Google Trends with Python using ScrapingBee
Version:  {version}
Requires: requests
Set SCRAPINGBEE_API_KEY in the environment before calling anything here.
"""
'''


def keep(node):
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.Import, ast.ImportFrom)):
        return True
    # constants only: CHAIN, NS, MAX_COMPARISON_ITEMS, RELATED_CHAIN
    if isinstance(node, ast.Assign):
        return all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)
    return False


def extract(block):
    lines = block.split("\n")
    tree = ast.parse(block)
    out, taken = [], set()
    for node in tree.body:
        if not keep(node):
            continue
        start = node.lineno - 1
        # pull in comment lines sitting directly above the node
        while start > 0 and lines[start - 1].lstrip().startswith("#") \
                and (start - 1) not in taken:
            start -= 1
        end = node.end_lineno
        taken.update(range(start, end))
        out.append("\n".join(lines[start:end]).rstrip())
    return out


def build():
    src = io.open(ART, encoding="utf-8").read()
    blocks = [b for lang, b in re.findall(r"```(\w*)\n(.*?)```", src, re.S)
              if lang == "python"]
    pieces = []
    for b in blocks:
        pieces.extend(extract(b))
    pieces = [p for p in pieces if p.strip()
              and p.strip() != "# Continues the same module."]
    seen, unique = set(), []
    for p in pieces:                       # imports repeat across blocks
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return HEADER.format(version=article_version(src)) + "\n" + "\n\n\n".join(unique) + "\n"


if __name__ == "__main__":
    if not os.path.exists(ART):
        print(f"Article markdown not found at {ART}.\n"
              "This script regenerates the module from the article's code blocks, so it\n"
              "needs that file. Set TRENDS_ARTICLE=/path/to/article.md, or run\n"
              "test_fixtures.py instead, which needs nothing outside this repo.")
        sys.exit(2)
    text = build()
    ast.parse(text)                        # refuse to write something broken
    if "--check" in sys.argv:
        current = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if current != text:
            print("google_trends.py is out of date; run python3 build.py")
            sys.exit(1)
        print("google_trends.py matches the article")
    else:
        io.open(OUT, "w", encoding="utf-8").write(text)
        print(f"wrote {OUT}, {len(text.splitlines())} lines")
