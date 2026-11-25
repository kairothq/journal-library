"""App settings in source/settings.json (kept on this Mac, file mode 600). Secrets never leave the server."""
import copy, hashlib, json, os, secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "source", "settings.json")

DEFAULTS = {
    "theme": {"lamp": "remember", "accent": "brass", "fonts": "classic", "hand": "caveat"},
    "reader": {"provider": "vision", "ollama_url": "http://localhost:11434", "ollama_model": "qwen2.5vl:3b",
               "anthropic_key": "", "anthropic_model": "claude-haiku-5-5", "bedrock_key": "", "bedrock_model": "google.gemma-3-12b-it"},
    "obsidian": {"folder": ""},  # e.g. ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<vault>/Daily logs
    "email": {"on": False, "to": "", "time": "08:00", "from": "", "app_password": "", "link": "", "last_sent": ""},
    "auth": {"salt": "", "hash": "", "lock_local": False},
}
SECRETS = {("reader", "anthropic_key"), ("reader", "bedrock_key"), ("email", "app_password")}

FONTS = {  # display serif, interface sans, Google Fonts query
    "classic": ("Young Serif", "Albert Sans", "family=Young+Serif&family=Albert+Sans:wght@400;500;600"),
    "editorial": ("Newsreader", "Figtree", "family=Newsreader:opsz,wght@6..72,500&family=Figtree:wght@400;500;600"),
    "soft": ("DM Serif Display", "DM Sans", "family=DM+Serif+Display&family=DM+Sans:wght@400;500;600"),
}
HANDS = {"caveat": ("Caveat", "family=Caveat:wght@500;600;700"), "kalam": ("Kalam", "family=Kalam:wght@400;700"),
         "patrick": ("Patrick Hand", "family=Patrick+Hand"), "gochi": ("Gochi Hand", "family=Gochi+Hand")}
ACCENTS = {"brass": ("#c99a5b", "#7a2a1a"), "forest": ("#8fbf8a", "#2f5a3a"), "ink": ("#9ab4e6", "#2b4a7a"), "plum": ("#d4a0c8", "#6a2a5a")}


def load():
    s = copy.deepcopy(DEFAULTS)
    try:
        with open(PATH) as f: saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict) and k in s: s[k].update(v)
    except FileNotFoundError:
        pass
    return s


def save(s):
    with open(PATH, "w") as f: json.dump(s, f, indent=1)
    os.chmod(PATH, 0o600)


def public(s):
    """Settings safe to send to the browser: secrets become has_* flags, the password hash is dropped."""
    out = copy.deepcopy(s)
    for sec, key in SECRETS:
        out[sec]["has_" + key] = bool(out[sec].pop(key))
    out["auth"] = {"has_password": bool(s["auth"]["hash"]), "lock_local": s["auth"]["lock_local"]}
    return out


def update(s, patch):
    for sec, vals in patch.items():
        if sec not in s or not isinstance(vals, dict): continue
        for k, v in vals.items():
            if sec == "auth" and k == "password":
                if v: set_password(s, v)
                continue
            if sec == "auth" and k == "clear_password":
                if v: s["auth"].update(salt="", hash="")
                continue
            if (sec, k) in SECRETS and v == "": continue  # empty means keep the saved key
            if k.startswith("clear_") and v: s[sec][k[6:]] = ""; continue
            if k in s[sec]: s[sec][k] = v
    return s


def set_password(s, pw):
    salt = secrets.token_hex(16)
    s["auth"]["salt"], s["auth"]["hash"] = salt, hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()


def check_password(s, pw):
    if not s["auth"]["hash"]: return False
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(s["auth"]["salt"]), 200_000).hex()
    return secrets.compare_digest(h, s["auth"]["hash"])


def theme_js(s):
    """Loaded in every page head: fonts, accent and lamp default, applied before first paint."""
    t = s["theme"]
    serif, sans, q1 = FONTS.get(t["fonts"], FONTS["classic"])
    hand, q2 = HANDS.get(t["hand"], HANDS["caveat"])
    dark, light = ACCENTS.get(t["accent"], ACCENTS["brass"])
    css = (f':root{{--serif:"{serif}",Georgia,serif;--sans:"{sans}",system-ui,sans-serif;--hand:"{hand}",cursive;--acc:{dark}}}'
           f':root[data-theme="light"]{{--acc:{light}}}')
    cfg = {"serif": serif, "sans": sans, "hand": hand, "lamp": t["lamp"]}
    return ("(function(){var h=document.head,l=document.createElement('link');l.rel='stylesheet';"
            f"l.href='https://fonts.googleapis.com/css2?{q1}&{q2}&display=swap';h.appendChild(l);"
            f"var st=document.createElement('style');st.textContent={json.dumps(css)};h.appendChild(st);"
            f"window.JR={json.dumps(cfg)};"
            "try{if(JR.lamp==='on')localStorage.setItem('lamp','on');if(JR.lamp==='off')localStorage.setItem('lamp','off');}catch(e){}"
            "try{if(localStorage.getItem('lamp')==='on')document.documentElement.dataset.theme='light';}catch(e){}})();")
