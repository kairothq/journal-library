"""Bring Obsidian daily logs (written by the Daily Log shortcut) into the journal. Read-only on the vault.

Each `YYYY-MM-DD.md` in the Daily logs folder becomes one entry on that date: the timestamped notes as
text, and every `![[photo]]` it embeds as a photo on the entry. Edited notes are picked up again;
notes deleted from Obsidian are removed here. Run: python3 scripts/obsidian_sync.py
"""
import hashlib, json, os, re, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build

import settings as cfg
VAULT_LOGS = os.path.expanduser(cfg.load()["obsidian"]["folder"])  # set in Settings > Daily Log
SPEC = f"{build.SRC}/pages.json"
EMBED = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
TIME = re.compile(r"^\*\*(\d{1,2}:\d{2})\*\*\s*$")


def parse(md):
    """-> (text with times kept, [embedded file names])"""
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)          # YAML front matter
    md = re.sub(r"```.*?```", "", md, flags=re.S)                     # habit tracker and other code blocks
    md = re.sub(r"%%.*?%%", "", md, flags=re.S)                       # Obsidian comments
    photos, lines = EMBED.findall(md), []
    for raw in EMBED.sub("", md).splitlines():
        line = raw.strip()
        if not line: continue
        m = TIME.match(line)
        if m:
            if lines: lines.append("")
            lines.append(m.group(1))
        else:
            clean = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", re.sub(r"[*_`#>]+", "", line)).strip()
            if clean and clean != "---": lines.append(clean)
    return "\n".join(lines).strip(), photos


def sync(build_after=True):
    if not VAULT_LOGS.strip():
        return {"error": "No Daily Log folder set in Settings", "days": 0}
    try:
        names = os.listdir(VAULT_LOGS)
    except OSError:
        return {"error": "Can't read the Daily logs folder yet", "days": 0}
    if not any(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", n) for n in names):
        return {"error": "No daily notes found there yet", "days": 0}  # never wipe entries because a folder looks empty
    spec = build.load_spec()
    old = {p["id"]: p for p in spec["pages"] if p.get("batch") == "obsidian"}
    keep, changed = {}, 0
    for name in sorted(names):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", name)
        if not m: continue
        path = os.path.join(VAULT_LOGS, name)
        try:
            with open(path, encoding="utf-8") as f: md = f.read()
        except OSError:
            continue  # iCloud placeholder not downloaded yet
        if not md.strip(): continue
        date, pid = m.group(1), f"O{m.group(1)}"
        digest = hashlib.sha1(("v2" + md).encode()).hexdigest()[:12]  # bump "v2" when parse() changes
        if pid in old and old[pid].get("digest") == digest:
            keep[pid] = old[pid]; continue
        text, photos = parse(md)
        dest = f"{build.SRC}/attachments/{pid}"
        shutil.rmtree(dest, ignore_errors=True); shutil.rmtree(f"{build.OUT}/attachments/{pid}", ignore_errors=True)
        atts = []
        for ph in photos:
            src = os.path.join(VAULT_LOGS, "attachments", ph)
            if not os.path.exists(src): src = os.path.join(VAULT_LOGS, ph)
            if not os.path.exists(src): continue
            os.makedirs(dest, exist_ok=True)
            out = os.path.join(dest, re.sub(r"[^A-Za-z0-9._-]", "_", os.path.splitext(ph)[0]) + ".jpg")
            r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "2000", src, "--out", out], capture_output=True)
            if not r.returncode: atts.append(f"attachments/{pid}/{os.path.basename(out)}")
        keep[pid] = {"id": pid, "batch": "obsidian", "typed": True, "source": "obsidian", "date_set": date, "title": "Daily log",
                     "text": text, "attachments": atts, "type": "journal", "dates": [], "digest": digest}
        changed += 1
    removed = [pid for pid in old if pid not in keep]
    for pid in removed:
        shutil.rmtree(f"{build.SRC}/attachments/{pid}", ignore_errors=True); shutil.rmtree(f"{build.OUT}/attachments/{pid}", ignore_errors=True)
    if changed or removed:
        spec["pages"] = [p for p in spec["pages"] if p.get("batch") != "obsidian"] + [keep[k] for k in sorted(keep)]
        with open(SPEC, "w") as f: json.dump(spec, f, indent=1, ensure_ascii=False)
        if build_after: build.build()
    return {"days": len(keep), "updated": changed, "removed": len(removed)}


if __name__ == "__main__":
    print(sync())
