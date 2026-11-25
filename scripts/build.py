"""Build page crops, date crops, the date brain and data.json for the review dashboard.

Inputs (source/): spreads/*.jpg, spreads/frames.json, pages.json, vision_ocr.jsonl, reviews.json (optional)
Outputs (out/):   pages/*.jpg, date_crops/*.jpg, data.json, brain.json
"""
import json, os, shutil, statistics
from datetime import date, timedelta
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC, OUT = os.path.join(ROOT, "source"), os.path.join(ROOT, "out")


def d(s): return date.fromisoformat(s)


def load_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except FileNotFoundError:
        return default


def load_spec():
    """source/pages.json, or an empty journal on a fresh install."""
    return load_json(f"{SRC}/pages.json", None) or {"pages": [], "gutters": {}, "video": None, "skipped_spreads": [], "batches": {}}


def crop_pages(spec):
    os.makedirs(f"{OUT}/pages", exist_ok=True)
    for p in spec["pages"]:
        if p.get("typed") or os.path.exists(f"{OUT}/pages/{p['id']}.jpg"): continue  # crops never change; keeps reviews fast at 150+ pages
        if p.get("src_image"):  # uploaded batches are already cut into pages
            shutil.copy(f"{SRC}/{p['src_image']}", f"{OUT}/pages/{p['id']}.jpg"); continue
        img = cv2.imread(f"{SRC}/spreads/{p['spread']}.jpg")
        h, w = img.shape[:2]
        g = int(spec["gutters"][p["spread"]] * w)
        page = img[:, :g] if p["side"] == "L" else img[:, g:]
        cv2.imwrite(f"{OUT}/pages/{p['id']}.jpg", page, [cv2.IMWRITE_JPEG_QUALITY, 88])


def vision_text(spread, side, gutter):
    """Raw macOS Vision lines that fall on this page half."""
    lines = []
    with open(f"{SRC}/vision_ocr.jsonl") as f:
        for row in map(json.loads, f):
            if row["file"] != f"{spread}.jpg": continue
            for l in row["lines"]:
                cx = l["x"] + l["w"] / 2
                if (cx < gutter) == (side == "L"):
                    lines.append(f"[{int(l['conf']*100)}] {l['text']}")
    return lines


def infer(spec, reviews):
    """Assign each page a date. Written dates are anchors; undated pages sit between anchors."""
    pages = [dict(p) for p in spec["pages"] if not p.get("blank")]
    # apply human corrections first: they become hard anchors
    for p in pages:
        r = reviews.get(p["id"], {})
        p["review"] = r
        if p.get("typed"): p["manual_date"] = p["date_set"]  # typed entries carry their own date
        for i, t in enumerate(p.get("dates", [])):
            tr = r.get("tokens", {}).get(str(i))
            if tr and tr.get("status") == "wrong" and tr.get("date"):
                t["corrected_from"], t["date"], t["source"], t["conf"] = t["date"], tr["date"], "you", 1.0
            elif tr and tr.get("status") == "right":
                t["source"], t["conf"] = t["source"] + " + you", 1.0
        if r.get("status") == "wrong" and r.get("date"):
            p["manual_date"] = r["date"]
        p["dropped"] = r.get("status") == "drop"  # still used as a date anchor, never resurfaced

    anchors = []  # (page index, date)
    for i, p in enumerate(pages):
        if p.get("manual_date"):
            anchors.append((i, d(p["manual_date"]), d(p["manual_date"])))
        elif p.get("dates"):
            ds = [d(t["date"]) for t in p["dates"]]
            anchors.append((i, min(ds), max(ds)))

    anomalies = []
    for (i1, _, a), (i2, b, _) in zip(anchors, anchors[1:]):
        if b < a:
            anomalies.append(f"{pages[i2]['id']} ({b}) is earlier than {pages[i1]['id']} ({a}). Check the reading or the page order.")

    for i, p in enumerate(pages):
        if p.get("manual_date"):
            p.update(date=p["manual_date"], kind="you", conf=1.0, range=[p["manual_date"]] * 2)
            continue
        if p.get("dates"):
            first = min(d(t["date"]) for t in p["dates"])
            p.update(date=str(first), kind="written", conf=min(t["conf"] for t in p["dates"]),
                     range=[str(first), str(max(d(t["date"]) for t in p["dates"]))])
            continue
        prev = next(((j, hi) for j, lo, hi in reversed(anchors) if j < i), None)
        nxt = next(((j, lo) for j, lo, hi in anchors if j > i), None)
        if prev and nxt:
            gap = (nxt[1] - prev[1]).days
            conf = 0.85 if gap <= 1 else 0.6 if gap <= 4 else 0.35
            if p.get("continues"): conf = max(conf, 0.9)
            p.update(date=str(prev[1]), kind="inferred", conf=conf, range=[str(prev[1]), str(nxt[1])],
                     why=f"No date on page. Sits after {pages[prev[0]]['id']} ({prev[1]:%d %b}) and before {pages[nxt[0]]['id']} ({nxt[1]:%d %b}); treated as a continuation of the earlier entry.")
        elif prev:
            p.update(date=str(prev[1]), kind="inferred", conf=0.9 if p.get("continues") else 0.4, range=[str(prev[1]), None],
                     why=f"No date on page and no later dated page yet. On or after {prev[1]:%d %b %Y}.")
        else:
            p.update(date=None, kind="unknown", conf=0, range=[None, None], why="No dated page before this one.")
        if p["review"].get("status") == "right" and p.get("date"):
            p["conf"], p["kind"] = 1.0, "inferred + you"

    # brain: the chronology and what comes next
    dates = sorted({d(p["manual_date"]) for p in pages if p.get("manual_date")} |
                   {d(t["date"]) for p in pages if not p.get("manual_date") for t in p.get("dates", [])})
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    med = statistics.median(gaps) if gaps else 1
    expected = [{"after": str(a), "next_written": str(b), "gap_days": (b - a).days,
                 "predicted": str(a + timedelta(days=round(med)))} for a, b in zip(dates, dates[1:])]
    brain = {
        "anchors": [{"page": pages[i]["id"], "date": str(lo) if lo == hi else f"{lo} to {hi}"} for i, lo, hi in anchors],
        "written_dates": [str(x) for x in dates],
        "order": "forward (each new spread is later than the last)",
        "gaps_days": gaps,
        "median_gap_days": med,
        "expected_vs_actual": expected,
        "next_expected_date": str(dates[-1] + timedelta(days=round(med))) if dates else None,
        "next_date_window": [str(dates[-1]), str(dates[-1] + timedelta(days=max(gaps) if gaps else 7))] if dates else None,
        "rules": [
            "Dates only move forward through the notebook. A reading that goes backwards is flagged, not trusted.",
            "Undated pages inherit the last written date (continuation) with a range up to the next written date.",
            "Year defaults to the last year seen (2025) when a date like '4 Nov' has no year.",
            "A date you confirm or correct becomes a hard anchor and re-dates the undated pages around it.",
        ],
        "anomalies": anomalies,
    }
    return pages, brain


def date_crops(spec, pages):
    out = f"{OUT}/date_crops"
    shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
    seq, crops = 0, {}
    for p in pages:
        crops[p["id"]] = []
        if p.get("typed"): continue
        if p.get("src_image"):  # whole image is the page; boxes are relative to it
            img, x0, gw = cv2.imread(f"{SRC}/{p['src_image']}"), 0.0, 1.0
        else:
            img, g = cv2.imread(f"{SRC}/spreads/{p['spread']}.jpg"), spec["gutters"][p["spread"]]
            x0, gw = (0.0, g) if p["side"] == "L" else (g, 1 - g)
        h, w = img.shape[:2]
        boxes = [(i, t["box"], t["date"], t["token"]) for i, t in enumerate(p.get("dates", []))]
        if not boxes:  # undated: crop the page header so you can see there is no date
            boxes = [("h", [x0, 0.0, gw, 0.14], p.get("date") or "unknown", "(no date written)")]
        for i, (x, y, bw, bh), dt, tok in boxes:
            seq += 1
            px, py = 0.02, 0.02
            x1, y1 = max(0, int((x - px) * w)), max(0, int((y - py) * h))
            x2, y2 = min(w, int((x + bw + px) * w)), min(h, int((y + bh + py) * h))
            tag = "written" if i != "h" else "UNDATED-guess"
            name = f"{seq:03d}_{p['id']}_{tag}_{dt}.jpg"
            cv2.imwrite(f"{out}/{name}", img[y1:y2, x1:x2], [cv2.IMWRITE_JPEG_QUALITY, 90])
            crops[p["id"]].append({"file": f"date_crops/{name}", "token": tok, "date": dt, "index": i})
    return crops


def build():
    spec = load_spec()
    frames = {f["id"]: f for f in load_json(f"{SRC}/spreads/frames.json", [])}
    reviews = load_json(f"{SRC}/reviews.json", {})
    crop_pages(spec)
    for p in spec["pages"]:  # photos added to entries
        for rel in p.get("attachments", []):
            if not os.path.exists(f"{OUT}/{rel}"):
                os.makedirs(os.path.dirname(f"{OUT}/{rel}"), exist_ok=True); shutil.copy(f"{SRC}/{rel}", f"{OUT}/{rel}")
    batches = {}  # each notebook/upload gets its own date chain; dates never carry across uploads
    for p in spec["pages"]: batches.setdefault(p.get("batch", "B1"), []).append(p)
    pages, brains = [], {}
    for b, ps in batches.items():
        got, brains[b] = infer({"pages": ps}, reviews)
        if b in ("typed", "demo", "obsidian"): brains[b]["anomalies"] = []
        pages += got
    main = [b for b in brains if b not in ("typed", "demo", "obsidian") and brains[b]["written_dates"]]
    brain = brains[main[-1]] if main else brains.get("B1") or (next(iter(brains.values())) if brains else infer({"pages": []}, reviews)[1])
    crops = date_crops(spec, pages)
    for p in pages:
        p["image"] = None if p.get("typed") else f"pages/{p['id']}.jpg"
        p["video_t"] = p.get("video_t") if "video_t" in p else frames.get(p.get("spread"), {}).get("t")
        p["vision"] = p.get("vision") or (vision_text(p["spread"], p["side"], spec["gutters"][p["spread"]]) if p.get("spread") in spec["gutters"] else [])
        p["date_crops"] = crops[p["id"]]
        if p.get("date") and not p["dropped"]:
            r = d(p["date"])
            p["resurface_on"] = str(r.replace(year=r.year + 1))
    meta = load_json(f"{SRC}/meta.json", {"pages": {}, "cats": []})
    for p in pages:
        pm = meta["pages"].get(p["id"], {})
        p["star"], p["note"], p["cats"] = bool(pm.get("star")), pm.get("note", ""), pm.get("cats", [])
        for k in ("text", "title"):  # your edits win over OCR and Obsidian
            if k in pm: p[k] = pm[k]
    data = {"categories": meta["cats"], "video": spec.get("video"), "skipped": spec.get("skipped_spreads", []), "pages": pages, "brain": brain, "batches": spec.get("batches", {}),
            "blank_pages": [p["id"] for p in spec["pages"] if p.get("blank")]}
    for name, obj in (("data.json", data), ("brain.json", brain)):
        with open(f"{OUT}/{name}", "w") as f: json.dump(obj, f, indent=1, ensure_ascii=False)
    return data


if __name__ == "__main__":
    data = build()
    for p in data["pages"]:
        print(p["id"], p["kind"].ljust(14), p.get("date"), p.get("range"), p.get("conf"))
    print(json.dumps(data["brain"], indent=1)[:1500])
