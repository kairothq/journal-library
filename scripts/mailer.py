"""Morning "On this day" email: pages written on today's date in past years, sent from a Gmail account with an app password.
Run by the app once a day at the time set in Settings. Test by hand: python3 scripts/mailer.py --test"""
import html, json, os, smtplib, subprocess, sys, tempfile
from datetime import date
from email.message import EmailMessage
from email.utils import make_msgid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build
import settings as cfg


def pages_on(day):
    """Pages from the same month and day in earlier years, newest year first."""
    try:
        with open(os.path.join(build.OUT, "data.json")) as f: data = json.load(f)
    except FileNotFoundError:
        return []
    md = day.strftime("-%m-%d")
    ps = [p for p in data["pages"] if not p.get("dropped") and (p.get("date") or "").endswith(md) and p["date"] < day.isoformat()]
    return sorted(ps, key=lambda p: p["date"], reverse=True)


def small_jpeg(path):
    """A copy at most 900px wide so the email stays light. Falls back to the original."""
    out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    r = subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "900", path, "--out", out], capture_output=True)
    with open(out if not r.returncode else path, "rb") as f: b = f.read()
    os.unlink(out); return b


def compose(day, ps, sender, to, link=""):
    m = EmailMessage()
    m["Subject"] = f"On this day: {day.day} {day:%B}" + (f", {len(ps)} page{'s' if len(ps) > 1 else ''} from past years" if ps else "")
    m["From"], m["To"] = sender, to
    plain, blocks, images = [], [], []
    for p in ps:
        y = int(p["date"][:4]); ago = day.year - y
        text = (p.get("text") or "").strip()
        snip = text[:700] + ("…" if len(text) > 700 else "")
        plain.append(f"{y} ({ago} year{'s' if ago > 1 else ''} ago)\n{p.get('title') or ''}\n{snip}\n")
        pic = p.get("image") or (p.get("attachments") or [None])[0]
        img = ""
        if pic and os.path.exists(os.path.join(build.OUT, pic)):
            cid = make_msgid()
            images.append((cid, os.path.join(build.OUT, pic)))
            img = f'<img src="cid:{cid[1:-1]}" alt="" style="display:block;max-width:100%;border-radius:6px;margin:12px 0">'
        blocks.append(f'''<div style="padding:22px 0;border-top:1px solid #e4d9c6">
<div style="font:600 26px Georgia,serif;color:#2f2418">{y}</div><div style="font:15px Georgia,serif;color:#8a7560;font-style:italic">{ago} year{'s' if ago > 1 else ''} ago</div>
{f'<div style="font:600 17px sans-serif;color:#8a3b22;margin-top:10px">{html.escape(p["title"])}</div>' if p.get("title") else ""}
{img}<div style="font:16px/1.55 Georgia,serif;color:#2f2418;white-space:pre-wrap">{html.escape(snip)}</div></div>''')
    if not ps:
        plain.append("Nothing was written on this day in past years.")
        blocks.append('<p style="font:16px Georgia,serif;color:#8a7560">Nothing was written on this day in past years.</p>')
    open_link = f'<p style="margin-top:26px"><a href="{html.escape(link)}" style="color:#8a3b22;font:600 15px sans-serif">Open your journal</a></p>' if link else ""
    m.set_content("\n".join(plain) + (f"\nOpen your journal: {link}" if link else ""))
    m.add_alternative(f'''<div style="background:#f3ead8;padding:28px 18px"><div style="max-width:560px;margin:0 auto">
<div style="font:400 34px Georgia,serif;color:#2f2418">On this day</div><div style="font:16px Georgia,serif;color:#8a7560;margin-bottom:14px">{day.day} {day:%B}</div>
{"".join(blocks)}{open_link}</div></div>''', subtype="html")
    html_part = m.get_payload()[1]
    for cid, path in images:
        html_part.add_related(small_jpeg(path), "image", "jpeg", cid=cid)
    return m


def send(e, day=None, test=False):
    """Sends today's email. Returns a short message. Skips quiet days unless it is a test."""
    day = day or date.today()
    if not (e.get("to") and e.get("from") and e.get("app_password")):
        raise ValueError("Fill in your Gmail address, its app password and where to send it.")
    ps = pages_on(day)
    if not ps and not test: return "Nothing written on this day in past years, so no email today."
    m = compose(day, ps, e["from"], e["to"], e.get("link", ""))
    if test: m.replace_header("Subject", "Test: " + m["Subject"])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(e["from"], e["app_password"].replace(" ", ""))
        s.send_message(m)
    return f"Sent to {e['to']} with {len(ps)} page{'s' if len(ps) != 1 else ''}."


if __name__ == "__main__":
    print(send(cfg.load()["email"], test="--test" in sys.argv))
