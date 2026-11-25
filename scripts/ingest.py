"""Turn an uploaded flip-through video or page photos into page images + dates.

Video: frames at 4fps -> still moments (page held steady) -> sharpest frame each -> drop repeats
       -> auto-rotate (whichever way macOS Vision reads most text) -> split spreads at the gutter
       -> OCR each page -> read written dates.
Photos: convert (HEIC ok) -> auto-rotate -> optional split -> OCR -> dates.
Returns page dicts for source/pages.json; the caller saves them and rebuilds.
"""
import glob, json, os, re, shutil, subprocess, tempfile
from datetime import date
import cv2
import numpy as np
import readers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source")
OCR = os.path.join(ROOT, "scripts", "ocr")

MONTH = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
         "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
         "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12}
MN = "|".join(sorted(MONTH, key=len, reverse=True))
R_DM = re.compile(rf"(?<![a-z])([0-9il|ogszb]{{1,2}})\s*(st|nd|rd|th)?\s*(?:of\s+)?({MN})\b\.?,?\s*('?\d{{4}}|'\d{{2}})?")
FIX = str.maketrans("il|ogszb", "11109526")  # handwriting OCR slips: Igth -> 19th
R_MD = re.compile(rf"\b({MN})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b,?\s*(\d{{4}})?")
R_NUM = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
DEADLINE = re.compile(r"(by|till|until|before|deadline|due|from)\s*$")


def ocr(paths):
    if not paths: return {}
    r = subprocess.run([OCR, *paths], capture_output=True, text=True)
    out = {}
    for line in r.stdout.splitlines():
        try: row = json.loads(line)
        except ValueError: continue
        out[row["file"]] = row["lines"]
    return out


def text_score(lines):
    return sum(len(l["text"]) * l["conf"] for l in lines)


def best_rotation(imgs, tmp):
    """Try 0/90/180/270 on a few sample images; keep whichever Vision reads most text from."""
    rots = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE]
    paths = []
    for i, im in enumerate(imgs):
        small = cv2.resize(im, None, fx=1200 / max(im.shape[:2]), fy=1200 / max(im.shape[:2]))
        for k, r in enumerate(rots):
            p = f"{tmp}/rot_{i}_{k}.jpg"; cv2.imwrite(p, small if r is None else cv2.rotate(small, r)); paths.append(p)
    res = ocr(paths)
    scores = [sum(text_score(res.get(f"rot_{i}_{k}.jpg", [])) for i in range(len(imgs))) for k in range(4)]
    return rots[int(np.argmax(scores))]


def gutter(img):
    """Darkest vertical band near the middle = the fold between two pages."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = g.shape
    col = g[int(h * .1):int(h * .9)].mean(axis=0)
    col = np.convolve(col, np.ones(15) / 15, mode="same")
    lo, hi = int(w * .38), int(w * .62)
    return (lo + int(np.argmin(col[lo:hi]))) / w


def still_frames(frame_paths):
    """One frame per page: find moments the page is held still, group shots of the same spread
    (ORB features + homography inliers: same page >100, different page <30), keep the sharpest."""
    G = [cv2.imread(p, cv2.IMREAD_GRAYSCALE) for p in frame_paths]
    sm = [cv2.resize(g, (96, int(96 * g.shape[0] / g.shape[1]))).astype(np.float32) for g in G]
    sharp = [cv2.Laplacian(cv2.resize(g, (640, int(640 * g.shape[0] / g.shape[1]))), cv2.CV_64F).var() for g in G]
    mo = [999.0] + [float(np.abs(a - b).mean()) for a, b in zip(sm[1:], sm)]
    if len(G) < 4: return list(range(len(G)))
    thr = float(np.percentile(mo[1:], 70))
    cand = [i for i in range(1, len(G)) if mo[i] <= thr and mo[i] <= min(mo[max(1, i - 2):i + 3])]
    orb, bf, K = cv2.ORB_create(1500), cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True), {}

    def feat(i):
        if i not in K: K[i] = orb.detectAndCompute(cv2.resize(G[i], (800, int(800 * G[i].shape[0] / G[i].shape[1]))), None)
        return K[i]

    def same(i, j):
        (ka, da), (kb, db) = feat(i), feat(j)
        if da is None or db is None: return False
        m = bf.match(da, db)
        if len(m) < 12: return False
        A = np.float32([ka[x.queryIdx].pt for x in m]); B = np.float32([kb[x.trainIdx].pt for x in m])
        _, mask = cv2.findHomography(A, B, cv2.RANSAC, 6.0)
        return mask is not None and int(mask.sum()) > 60

    best_of = lambda g: max(g, key=lambda k: sharp[k])
    groups = []
    for i in cand:
        if groups and same(groups[-1][-1], i): groups[-1].append(i)
        else: groups.append([i])
    merged = []  # a group that starts on a blurry frame can miss its page; merge groups whose best shots match
    for g in groups:
        tgt = next((m for m in merged if same(best_of(m), best_of(g))), None)
        if tgt: tgt.extend(g)
        else: merged.append(list(g))
    groups = merged
    picks = []
    for g in groups:
        best = best_of(g)
        for n in range(max(0, min(g) - 2), min(len(G), max(g) + 3)):  # a sharper neighbour of the same page
            if n not in g and sharp[n] > sharp[best] * 1.3 and same(best, n): best = n
        dup = next((k for k, p in enumerate(picks) if same(p, best)), None)
        if dup is None: picks.append(best)
        elif sharp[best] > sharp[picks[dup]]: picks[dup] = best
    return picks


def parse_dates(lines, year):
    found = []
    for l in lines:
        t = l["text"].lower()
        for m in list(R_DM.finditer(t)) + list(R_MD.finditer(t)) + list(R_NUM.finditer(t)):
            if DEADLINE.search(t[:m.start()][-12:]): continue
            g = m.groups()
            try:
                if m.re is R_DM:
                    if not g[0].isdigit() and not g[1]: continue  # letters-as-digits only with st/nd/rd/th
                    dd, mm, yy = int(g[0].translate(FIX)), MONTH[g[2]], g[3]
                elif m.re is R_MD: dd, mm, yy = int(g[1]), MONTH[g[0]], g[2]
                else: dd, mm, yy = int(g[0]), int(g[1]), g[2]
                y = int(yy.strip("'")) if yy else None
                if y is not None and y < 100: y += 2000
                dt = date(y or year, mm, dd)
            except (ValueError, KeyError):
                continue
            found.append({"token": l["text"][m.start():m.end()].strip(), "date": str(dt), "box": [round(l[k], 3) for k in "xywh"],
                          "source": "vision", "conf": round(min(.9, .5 + .4 * l["conf"]), 2), "has_year": bool(yy)})
    seen, out = set(), []
    for f in found:
        if f["date"] not in seen: seen.add(f["date"]); out.append(f)
    return out


def run(batch, files, kind, year, spreads, prefix, progress=lambda stage, pct: None, reader=None):
    """files: uploaded file paths. Returns (pages, info)."""
    out_dir = os.path.join(SRC, "batches", batch); os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=out_dir, prefix="tmp_")
    try:
        imgs, times = [], []
        if kind == "video":
            progress("Pulling frames out of the video", 5)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-i", files[0], "-vf",
                            "fps=4,scale='if(gt(iw,ih),1920,-2)':'if(gt(iw,ih),-2,1920)'", "-q:v", "3", f"{tmp}/f_%05d.jpg"], check=True)
            frames = sorted(glob.glob(f"{tmp}/f_*.jpg"))
            progress(f"Finding the moments each page is held still ({len(frames)} frames)", 25)
            keep = still_frames(frames)
            imgs = [cv2.imread(frames[i]) for i in keep]; times = [round(i / 4, 2) for i in keep]
        else:
            progress("Reading photos", 10)
            for i, f in enumerate(files):
                j = f"{tmp}/p_{i:04d}.jpg"
                subprocess.run(["sips", "-s", "format", "jpeg", f, "--out", j], capture_output=True)
                im = cv2.imread(j)
                if im is not None: imgs.append(im); times.append(None)
        if not imgs: raise RuntimeError("Couldn't find any steady pages in this upload.")

        progress(f"Working out which way is up ({len(imgs)} shots)", 45)
        if kind == "video":
            rot = best_rotation(imgs[:3], tmp)
            imgs = [im if rot is None else cv2.rotate(im, rot) for im in imgs]
        else:
            imgs = [im if (r := best_rotation([im], tmp)) is None else cv2.rotate(im, r) for im in imgs]

        progress("Splitting spreads into pages" if spreads else "Saving pages", 60)
        page_imgs = []  # (img, shot index, side)
        for s, im in enumerate(imgs):
            if spreads and im.shape[1] > im.shape[0] * .9:
                g = int(gutter(im) * im.shape[1])
                page_imgs += [(im[:, :g], s, "L"), (im[:, g:], s, "R")]
            else:
                page_imgs.append((im, s, None))
        paths = []
        for k, (im, s, side) in enumerate(page_imgs):
            pid = f"{prefix}{k + 1:03d}"; p = f"{out_dir}/{pid}.jpg"
            cv2.imwrite(p, im, [cv2.IMWRITE_JPEG_QUALITY, 88]); paths.append((pid, p, s, side))

        progress(f"Reading {len(paths)} pages with macOS Vision", 70)
        res = ocr([p for _, p, _, _ in paths])
        pages, last, errors = [], None, []
        for pid, p, s, side in paths:
            lines = res.get(os.path.basename(p), [])
            ds = parse_dates(lines, year)
            good = [l for l in lines if l["conf"] > .3 and len(l["text"]) > 2]
            title = next((l["text"] for l in good if sum(c.isalpha() for c in l["text"]) >= 3), "")
            text, via = "\n".join(l["text"] for l in lines), "vision"
            if reader and reader.get("provider", "vision") != "vision" and len(good) >= 2:
                progress(f"Reading page {len(pages) + 1} of {len(paths)} with {reader['provider']}", 70 + int(20 * len(pages) / len(paths)))
                try:
                    r = readers.read(reader, p, year)
                    text, title, via = r["text"] or text, r["title"] or title, reader["provider"]
                    ds = [{"token": d, "date": d, "box": [0, 0, 1, .14], "source": via, "conf": .85, "has_year": True} for d in r["dates"]]
                except Exception as e:  # fall back to what Vision read
                    errors.append(str(e)[:160])
            for t in ds:  # a journal moves forward: '3 Jan' after '28 Dec' is next year
                dt = date.fromisoformat(t["date"])
                if last and not t.pop("has_year") and (last - dt).days > 60:
                    dt = dt.replace(year=dt.year + 1); t["date"] = str(dt)
                else: t.pop("has_year", None)
                last = max(last, dt) if last else dt
            pages.append({"id": pid, "batch": batch, "src_image": f"batches/{batch}/{pid}.jpg", "side": side, "shot": s,
                          "video_t": times[s], "title": title[:60], "text": text, "read_by": via,
                          "vision": [f"[{int(l['conf'] * 100)}] {l['text']}" for l in lines], "dates": ds,
                          "type": "journal", **({"blank": True} if len(good) < 2 else {})})
        info = {"reader_errors": errors[:3], "shots": len(imgs), "pages": len(pages), "blank": sum(1 for p in pages if p.get("blank")),
                "dates": sum(len(p["dates"]) for p in pages)}
        return pages, info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":  # dry run: python3 scripts/ingest.py video.mov [year] [--single]
    import sys
    f = sys.argv[1]; yr = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else date.today().year
    kind = "video" if f.lower().endswith((".mov", ".mp4", ".m4v")) else "photos"
    pages, info = run("DRYRUN", [f], kind, yr, "--single" not in sys.argv, "DRY-", lambda s, p: print(f"{p:3d}% {s}"))
    print(info)
    for p in pages: print(p["id"], p["side"], p.get("blank", ""), p["video_t"], p["title"][:30], [t["date"] for t in p["dates"]])
