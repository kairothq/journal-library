"""Local journal app. Run: python3 scripts/server.py  ->  http://localhost:8765
  /         review dates (right / wrong / drop)
  /library  3D bookshelf
  /add      upload a video or photos, or write an entry
Saves your calls to source/reviews.json, new pages to source/pages.json, and rebuilds after every change."""
import json, os, re, subprocess, sys, threading, time, uuid
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build, ingest, mailer, obsidian_sync, readers
import settings as cfg
import secrets as tokens

ROOT = build.ROOT
REVIEWS = os.path.join(ROOT, "source", "reviews.json")
SPEC = os.path.join(ROOT, "source", "pages.json")
META = os.path.join(ROOT, "source", "meta.json")  # stars, notes, categories
UPLOADS = os.path.join(ROOT, "source", "uploads")
LOCK = threading.Lock()  # one writer at a time for pages.json / reviews.json / out/
JOBS = {}
OBSIDIAN = {}  # last Daily logs sync
MAIL = {}  # last morning email
PORT = int(os.environ.get("JOURNAL_PORT", "8765"))
PAGES = {"/": "index.html", "/index.html": "index.html", "/library": "library.html", "/library.html": "library.html", "/add": "add.html", "/add.html": "add.html", "/settings": "settings.html", "/login": "login.html"}
SESSIONS_PATH = os.path.join(ROOT, "source", "sessions.json")
SESSION_DAYS = 30


def logs_dir():
    """The Obsidian folder if this process may read it, else the copy JournalSync.app keeps in source/obsidian_mirror."""
    d = os.path.expanduser(cfg.load()["obsidian"]["folder"])
    if not d.strip(): return ""
    try:
        os.listdir(d); return d
    except OSError:
        return os.path.join(ROOT, "source", "obsidian_mirror")


def sessions():
    s = build.load_json(SESSIONS_PATH, {})
    now = time.time()
    return {k: v for k, v in s.items() if v > now}


def save_sessions(s):
    with open(SESSIONS_PATH, "w") as f: json.dump(s, f)
    os.chmod(SESSIONS_PATH, 0o600)


def save_spec(spec):
    with open(SPEC, "w") as f: json.dump(spec, f, indent=1, ensure_ascii=False)


def next_entry_id(spec):
    nums = [int(p["id"][1:]) for p in spec["pages"] if re.match(r"E\d+$", p["id"])]
    return f"E{max(nums, default=0) + 1:03d}"


def next_batch(spec):
    taken = set(spec.get("batches", {})) | {j["batch"] for j in JOBS.values()}
    nums = [int(b[1:]) for b in taken if b[1:].isdigit()] + [1]
    return f"B{max(nums) + 1}"


def process(job):
    def progress(stage, pct): job.update(stage=stage, pct=pct)
    try:
        pages, info = ingest.run(job["batch"], job["files"], job["kind"], job["year"], job["spreads"], f"{job['batch']}-", progress, cfg.load()["reader"])
        progress("Placing pages on their dates", 92)
        with LOCK:
            spec = build.load_spec()
            spec["pages"] += pages
            spec.setdefault("batches", {})[job["batch"]] = {"kind": job["kind"], "name": job["name"], "year": job["year"],
                                                          "added": time.strftime("%Y-%m-%d %H:%M"), **info}
            save_spec(spec)
            build.build()
        job.update(stage="Done", pct=100, done=True, info=info, ids=[p["id"] for p in pages])
    except Exception as e:
        job.update(stage="Failed", error=str(e)[:300], done=True)


class H(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?")[0]
        if path in PAGES: return os.path.join(ROOT, "web", PAGES[path])
        return os.path.join(ROOT, "out", path.lstrip("/"))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reply(self, obj, code=200):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

    # ---- login: asked for whenever the app is reached from outside this Mac (or always, if you lock it)
    def remote(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return bool(self.headers.get("Cf-Connecting-Ip") or self.headers.get("X-Forwarded-For")) or host not in ("localhost", "127.0.0.1", "")

    def gate(self):
        """None when the request may go ahead, else 'login' or 'nopass'."""
        s = cfg.load()
        if not s["auth"]["hash"]: return "nopass" if self.remote() else None
        if not (self.remote() or s["auth"]["lock_local"]): return None
        tok = next((c.split("=", 1)[1] for c in (self.headers.get("Cookie") or "").split("; ") if c.startswith("jr_session=")), "")
        return None if tok and tok in sessions() else "login"

    def blocked(self, why):
        if why == "nopass":
            msg = b"Set a password in Settings on your Mac before opening the journal from another device."
            self.send_response(403); self.send_header("Content-Type", "text/plain"); self.send_header("Content-Length", str(len(msg))); self.end_headers(); self.wfile.write(msg); return
        if self.command == "GET" and self.path.split("?")[0] in PAGES:
            self.path = "/login"; return super().do_GET()
        self.reply({"error": "Log in first"}, 401)

    def do_GET(self):
        if self.path.startswith("/theme.js"):
            out = cfg.theme_js(cfg.load()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/javascript"); self.send_header("Content-Length", str(len(out))); self.end_headers()
            return self.wfile.write(out)
        if self.path.split("?")[0] == "/login": return super().do_GET()
        why = self.gate()
        if why: return self.blocked(why)
        if self.path.startswith("/api/settings"): return self.reply(cfg.public(cfg.load()))
        if self.path.startswith("/api/obsidian"): return self.reply(OBSIDIAN)
        if self.path.startswith("/api/email"): return self.reply(MAIL)
        if self.path.startswith("/api/jobs"):
            return self.reply(sorted(({k: v for k, v in j.items() if k != "files"} for j in JOBS.values()), key=lambda j: -j["t"]))
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/login": return self.login(self.body())
        why = self.gate()
        if why: return self.blocked(why)
        if u.path == "/api/logout": return self.logout()
        if u.path == "/api/settings": return self.save_settings(self.body())
        if u.path == "/api/settings/test": return self.test_reader(self.body())
        if u.path == "/api/obsidian/sync": return self.obsidian_now()
        if u.path == "/api/email/test": return self.email_test()
        if u.path == "/api/upload": return self.upload(parse_qs(u.query))
        if u.path == "/api/process": return self.start(self.body())
        if u.path == "/api/entry": return self.entry(self.body())
        if u.path == "/api/attach": return self.attach(parse_qs(u.query))
        if u.path == "/api/meta": return self.meta(self.body())
        if u.path == "/api/cats": return self.cats(self.body())
        if u.path == "/api/review": return self.review(self.body())
        self.send_error(404)

    def upload(self, q):
        """Raw file body, streamed to source/uploads/<upload id>/<name>."""
        uid = re.sub(r"[^A-Za-z0-9_-]", "", q.get("upload", [""])[0]) or uuid.uuid4().hex[:10]
        name = os.path.basename(q.get("name", ["file"])[0]).replace("/", "_") or "file"
        d = os.path.join(UPLOADS, uid); os.makedirs(d, exist_ok=True)
        left = int(self.headers["Content-Length"])
        with open(os.path.join(d, name), "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk: break
                f.write(chunk); left -= len(chunk)
        self.reply({"upload": uid, "name": name})

    def login(self, b):
        s = cfg.load()
        if not cfg.check_password(s, b.get("password", "")):
            time.sleep(1); return self.reply({"error": "That password isn't right"}, 401)
        tok = tokens.token_urlsafe(32)
        ss = sessions(); ss[tok] = time.time() + SESSION_DAYS * 86400; save_sessions(ss)
        secure = "; Secure" if self.remote() else ""
        out = b'{"ok": true}'
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.send_header("Set-Cookie", f"jr_session={tok}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS * 86400}{secure}")
        self.end_headers(); self.wfile.write(out)

    def logout(self):
        tok = next((c.split("=", 1)[1] for c in (self.headers.get("Cookie") or "").split("; ") if c.startswith("jr_session=")), "")
        ss = sessions(); ss.pop(tok, None); save_sessions(ss)
        out = b'{"ok": true}'
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(out)))
        self.send_header("Set-Cookie", "jr_session=; Path=/; Max-Age=0"); self.end_headers(); self.wfile.write(out)

    def save_settings(self, b):
        with LOCK:
            s = cfg.update(cfg.load(), b); cfg.save(s)
        self.reply(cfg.public(s))

    def test_reader(self, b):
        r = dict(cfg.load()["reader"]); r.update({k: v for k, v in b.items() if v not in ("", None)})
        try: self.reply({"ok": True, "message": readers.test(r)})
        except Exception as e: self.reply({"ok": False, "message": str(e)[:240]})

    def email_test(self):
        try: self.reply({"ok": True, "message": mailer.send(cfg.load()["email"], test=True)})
        except Exception as e: self.reply({"ok": False, "message": mail_error(e)})

    def obsidian_now(self):
        with LOCK:
            obsidian_sync.VAULT_LOGS = logs_dir()
            OBSIDIAN.clear(); OBSIDIAN.update(obsidian_sync.sync(), at=time.strftime("%H:%M"))
        self.reply(OBSIDIAN)

    def save_meta(self, m):
        with open(META, "w") as f: json.dump(m, f, indent=1, ensure_ascii=False)

    def meta(self, b):
        """Star, note or categories for one page."""
        with LOCK:
            m = build.load_json(META, {"pages": {}, "cats": []})
            pm = m["pages"].setdefault(b["page"], {})
            for k in ("star", "note", "cats", "text", "title"):
                if k in b: pm[k] = b[k]
            self.save_meta(m)
            data = build.build()
        self.reply(data)

    def cats(self, b):
        """Add, rename or delete a category. Subcategories carry a parent id."""
        with LOCK:
            m = build.load_json(META, {"pages": {}, "cats": []})
            if b["op"] == "add":
                name = (b.get("name") or "").strip()[:40]
                if not name: return self.reply({"error": "Give the category a name"}, 400)
                cid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "cat"
                while any(c["id"] == cid for c in m["cats"]): cid += "-2"
                m["cats"].append({"id": cid, "name": name, "parent": b.get("parent") or None})
            elif b["op"] == "rename":
                for c in m["cats"]:
                    if c["id"] == b["id"]: c["name"] = (b.get("name") or c["name"]).strip()[:40]
            elif b["op"] == "delete":
                gone = {b["id"]} | {c["id"] for c in m["cats"] if c.get("parent") == b["id"]}
                m["cats"] = [c for c in m["cats"] if c["id"] not in gone]
                for pm in m["pages"].values(): pm["cats"] = [c for c in pm.get("cats", []) if c not in gone]
            self.save_meta(m)
            data = build.build()
        self.reply(data)

    def attach(self, q):
        """A photo added to an entry: raw body, saved as source/attachments/<page>/<name>.jpg."""
        pid = q.get("page", [""])[0]
        name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(q.get("name", ["photo.jpg"])[0])) or "photo.jpg"
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with LOCK:
            if not any(p["id"] == pid for p in build.load_spec()["pages"]):
                return self.reply({"error": "That entry no longer exists"}, 404)
        d = os.path.join(ROOT, "source", "attachments", pid); os.makedirs(d, exist_ok=True)
        raw = os.path.join(d, f"{int(time.time() * 1000)}_{name}")
        with open(raw, "wb") as f: f.write(body)
        out = os.path.splitext(raw)[0] + ".jpg"
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "2000", raw, "--out", out], capture_output=True)
        if raw != out: os.remove(raw)
        if r.returncode or not os.path.exists(out): return self.reply({"error": "That file isn't a photo"}, 400)
        rel = f"attachments/{pid}/{os.path.basename(out)}"
        with LOCK:
            spec = build.load_spec()
            page = next(p for p in spec["pages"] if p["id"] == pid)
            page["attachments"] = page.get("attachments", []) + [rel]
            save_spec(spec)
            build.build()
        self.reply({"file": rel})

    def start(self, b):
        uid = re.sub(r"[^A-Za-z0-9_-]", "", b["upload"])
        d = os.path.join(UPLOADS, uid)
        files = sorted(os.path.join(d, f) for f in os.listdir(d))
        kind = "video" if any(f.lower().endswith((".mov", ".mp4", ".m4v", ".avi", ".webm")) for f in files) else "photos"
        if kind == "video": files = [next(f for f in files if f.lower().endswith((".mov", ".mp4", ".m4v", ".avi", ".webm")))]
        with LOCK:
            batch = next_batch(build.load_spec())
        job = {"id": uid, "batch": batch, "kind": kind, "name": b.get("name") or os.path.basename(files[0]), "files": files,
               "year": int(b.get("year") or date.today().year), "spreads": bool(b.get("spreads", True)),
               "stage": "Queued", "pct": 0, "done": False, "t": time.time()}
        JOBS[uid] = job
        threading.Thread(target=process, args=(job,), daemon=True).start()
        self.reply({k: v for k, v in job.items() if k != "files"})

    def entry(self, b):
        try: date.fromisoformat(b["date"])
        except (KeyError, ValueError): return self.reply({"error": "Pick a date"}, 400)
        if not (b.get("text") or "").strip(): return self.reply({"error": "Write something first"}, 400)
        with LOCK:
            spec = build.load_spec()
            pid = next_entry_id(spec)
            spec["pages"].append({"id": pid, "batch": "typed", "typed": True, "date_set": b["date"], "title": (b.get("title") or "").strip()[:80],
                                  "text": b["text"].strip(), "type": b.get("type") if b.get("type") in ("journal", "notes") else "journal", "dates": []})
            save_spec(spec)
            build.build()
        self.reply({"id": pid})

    def review(self, body):
        with LOCK:
            before = {p["id"]: p.get("date") for p in build.load_json(os.path.join(ROOT, "out", "data.json"), {"pages": []})["pages"]}
            reviews = build.load_json(REVIEWS, {})
            ids = body["page"] if isinstance(body["page"], list) else [body["page"]]
            for pid in ids:
                if body["status"] == "clear":
                    reviews.pop(pid, None)
                else:
                    reviews[pid] = {"status": body["status"], "date": body.get("date") or None}
            with open(REVIEWS, "w") as f:
                json.dump(reviews, f, indent=1)
            data = build.build()
        data["changed"] = [p["id"] for p in data["pages"] if p["id"] not in ids and before.get(p["id"]) != p.get("date")]
        self.reply(data)

    def log_message(self, *a):
        pass


def mail_error(e):
    if "Username and Password not accepted" in str(e) or "BadCredentials" in str(e):
        return "Gmail turned down the login. Check the address and use an app password, not your normal password."
    return str(e)[:240]


def email_loop():
    """Once a day, at or after the time in Settings, send the On this day email. A Mac that was asleep at that time sends when it wakes."""
    while True:
        try:
            s = cfg.load(); e = s["email"]; today = date.today().isoformat()
            if e["on"] and e["last_sent"] != today and time.strftime("%H:%M") >= e["time"]:
                MAIL.update(message=mailer.send(e), ok=True, at=time.strftime("%H:%M"))
                with LOCK:
                    s = cfg.load(); s["email"]["last_sent"] = today; cfg.save(s)
        except Exception as ex:
            MAIL.update(message=mail_error(ex), ok=False, at=time.strftime("%H:%M"))
            time.sleep(1800)  # don't hammer Gmail with a bad password
        time.sleep(60)


def obsidian_loop():
    """Pull new Daily Log notes from Obsidian every 5 minutes while the app runs."""
    while True:
        try:
            with LOCK:
                obsidian_sync.VAULT_LOGS = logs_dir()
                OBSIDIAN.clear(); OBSIDIAN.update(obsidian_sync.sync(), at=time.strftime("%H:%M"))
        except Exception as e:
            OBSIDIAN.update(error=str(e)[:200], at=time.strftime("%H:%M"))
        time.sleep(300)


if __name__ == "__main__":
    threading.Thread(target=obsidian_loop, daemon=True).start()
    threading.Thread(target=email_loop, daemon=True).start()
    build.build()
    print(f"Journal app on http://localhost:{PORT}  (review /, library /library, add /add)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
