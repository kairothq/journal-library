"""Builds a read-only, always-on demo of the app (no Mac needed) into site/, from whatever is in this checkout.
Use it on a fresh clone filled with the sample journal, never on your real one:
  python3 scripts/demo.py add && python3 scripts/demo_site.py
  cd site && npx wrangler pages deploy public --project-name <name>"""
import json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import settings as cfg

ROOT, SITE = build.ROOT, os.path.join(build.ROOT, "site")
PUB = os.path.join(SITE, "public")
REPO = "https://github.com/kairothq/journal-library"
NOTE = (f'<a href="{REPO}" target="_blank" rel="noopener" style="position:fixed;left:16px;bottom:16px;z-index:30;'
        'background:rgba(20,14,9,.82);color:#f3e6cf;border:1px solid rgba(239,227,207,.25);border-radius:999px;padding:8px 14px;'
        'font:500 13px system-ui,sans-serif;text-decoration:none;backdrop-filter:blur(6px)">A sample journal. Make your own on GitHub</a>')
API = """// The demo has no Mac behind it: reads get sample answers, saves are politely refused.
const SETTINGS = %s;
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { "content-type": "application/json" } });
export async function onRequest({ request, params }) {
  const path = [].concat(params.path || []).join("/");
  if (request.method === "GET") return json(path === "settings" ? SETTINGS : path === "jobs" ? [] : {});
  const message = "This is a sample journal, so nothing is saved. Make your own copy from GitHub.";
  return json({ ok: false, error: message, message }, 403);
}
"""


def main():
    data = os.path.join(build.OUT, "data.json")
    with open(data) as f: d = json.load(f)
    if any(not p.get("demo") for p in d["pages"]):
        sys.exit("This checkout has real pages in it. Run this on a fresh clone with only the sample journal.")
    shutil.rmtree(SITE, ignore_errors=True)
    shutil.copytree(build.OUT, PUB)
    pages = {"library.html": "library.html", "index.html": "review.html", "add.html": "add.html", "settings.html": "settings.html"}
    for src, dst in pages.items():
        with open(os.path.join(ROOT, "web", src)) as f: h = f.read()
        h = re.sub(r'href="/"', 'href="/review"', h)
        h = h.replace("</body>", NOTE + "\n</body>")
        with open(os.path.join(PUB, dst), "w") as f: f.write(h)
    with open(os.path.join(PUB, "index.html"), "w") as f:
        f.write('<!doctype html><meta http-equiv="refresh" content="0; url=/library"><title>Journal Library</title><a href="/library">Open the library</a>')
    s = cfg.load() if os.path.exists(cfg.PATH) else cfg.DEFAULTS
    with open(os.path.join(PUB, "theme.js"), "w") as f: f.write(cfg.theme_js(s))
    os.makedirs(os.path.join(SITE, "functions", "api"), exist_ok=True)
    with open(os.path.join(SITE, "functions", "api", "[[path]].js"), "w") as f:
        f.write(API % json.dumps(cfg.public(cfg.DEFAULTS)))
    print(f"Demo site in {SITE}. Deploy it with: cd site && npx wrangler pages deploy public --project-name <name>")


if __name__ == "__main__":
    main()
