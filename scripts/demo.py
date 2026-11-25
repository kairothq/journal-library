"""Sample journal so you can see the library full before adding your own pages.
  python3 scripts/demo.py add      adds made-up entries across the last six years (marked demo), with categories,
                                   stars and a few handwritten page photos. Today always has two entries.
  python3 scripts/demo.py remove   deletes only the demo entries; anything you added stays
Everything here is invented. Same seed, same journal."""
import json, os, random, shutil, sys, textwrap
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build

SPEC, META = f"{build.SRC}/pages.json", f"{build.SRC}/meta.json"

CATS = [("work", "Work", None), ("projects", "Projects", "work"), ("career", "Career moves", "work"),
        ("health", "Health", None), ("running", "Running", "health"), ("sleep", "Sleep", "health"),
        ("people", "People", None), ("family", "Family", "people"), ("friends", "Friends", "people"),
        ("ideas", "Ideas", None), ("travel", "Travel", None), ("good-days", "Good days", None)]

ENTRIES = [
    ("First 5k without stopping", "Slow, but I didn't walk once. Legs like jelly after. Going to sign up for the river run in spring.", ["running", "good-days"]),
    ("Rainy Sunday", "Made soup, read half a novel, called Mum. Nothing happened and it was perfect.", ["family", "good-days"]),
    ("New job, day one", "The studio is smaller than it looked online. Everyone is kind. I don't know where anything is yet.", ["career"]),
    ("Couldn't sleep", "Up at 3 again, thinking about money. Wrote a list instead of scrolling. Felt better by 4.", ["sleep"]),
    ("Biscuit learnt to sit", "Took two weeks of treats. He now sits for everything, including when I just look at him.", ["good-days"]),
    ("Moving boxes", "Packed the whole kitchen in one evening. How do I own eleven mugs.", ["family"]),
    ("Lisbon, day two", "Got lost on purpose. Custard tarts for breakfast and lunch. The light here is unreal at six.", ["travel", "good-days"]),
    ("Pitched the redesign", "Nervous for an hour before, fine once I started. They want a second version by Friday.", ["projects"]),
    ("Idea: a tool library", "What if our street shared one drill, one ladder, one pressure washer. Sign-out sheet on the door.", ["ideas"]),
    ("Long walk with Sam", "Two hours by the canal, talked about everything. Old friends are a kind of home.", ["friends"]),
    ("Bad run", "Side stitch at 2k, turned back. Some days the body just says no. Rest tomorrow.", ["running"]),
    ("Dad's birthday", "Cooked his favourite, it was too salty, he ate two plates anyway.", ["family", "good-days"]),
    ("Quarter review", "Shipped two things, dropped one. Need to say no earlier instead of late.", ["work"]),
    ("Started pottery", "My bowl is a plate. The teacher says everyone's first bowl is a plate.", ["good-days"]),
    ("Asked for a raise", "Practised in the mirror. They said they'd come back to me in two weeks. Proud I asked.", ["career"]),
    ("Slept eight hours", "Phone out of the bedroom for a week now. It works and I hate that it works.", ["sleep", "health"]),
    ("Train to the coast", "Window seat, sea the whole last hour. Wrote three pages without trying.", ["travel"]),
    ("Side project launch", "Put the recipe app online. Eleven people signed up, four of them were my friends.", ["projects", "ideas"]),
    ("Friday dinner", "Six of us around a table built for four. Someone brought a guitar. Nobody could play.", ["friends", "good-days"]),
    ("Half marathon", "2:14. Cried a little at the finish. Last year I couldn't run for a bus.", ["running", "good-days"]),
    ("Hard conversation", "Told Priya I felt left out. She hadn't noticed. We're okay. Glad I said it out loud.", ["friends"]),
    ("Learning to cook dal", "Third try. Finally tastes like Nani's, or close enough that I'm calling it.", ["family"]),
    ("Work trip to Berlin", "Two days of meetings, one evening free. Walked until my feet hurt.", ["travel", "work"]),
    ("Idea: morning pages app", "A notebook that reminds you what you wrote a year ago today. Probably exists already.", ["ideas"]),
    ("Snow day", "Office closed. Built a terrible snowman with the neighbour's kids.", ["good-days"]),
    ("Burnt out", "Third late night this week. Booking a day off before I start resenting everything.", ["work", "health"]),
    ("New flat", "Unpacked the books first, then everything else. The window gets sun all afternoon.", ["good-days"]),
    ("Gym, week four", "Not a gym person, still not a gym person, but I keep going back.", ["health"]),
    ("Promotion", "Lead designer from next month. Called Mum before I'd even left the building.", ["career", "family", "good-days"]),
    ("Night swim", "Lake was freezing. We stayed in for ten minutes and talked about it for an hour.", ["friends", "travel"]),
    ("Plan for next year", "Fewer projects, more finishing. Run a full marathon. See Grandma more often.", ["ideas"]),
    ("Kyoto, last day", "Woke early for the temple before the crowds. Stood there for a long time.", ["travel"]),
    ("Back pain", "Desk is too low. Ordered a stand, put books under the laptop for now.", ["health"]),
    ("Mentor lunch", "She said the work gets easier when you stop trying to be liked by it. Thinking about that.", ["career"]),
    ("Market Saturday", "Bought too many tomatoes, gave half to the neighbour, got a jar of jam back.", ["good-days"]),
]


def render_page(title, text, d, out):
    """A photo of a handwritten notebook page."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    rnd = random.Random(title)
    W, H = 900, 1200
    page = Image.new("RGB", (W, H), (246, 240, 226))
    dr = ImageDraw.Draw(page)
    for y in range(170, H - 60, 56): dr.line([(40, y), (W - 40, y)], fill=(196, 210, 228), width=2)
    dr.line([(120, 0), (120, H)], fill=(226, 160, 160), width=2)
    fonts = ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf", "/System/Library/Fonts/Noteworthy.ttc", "/System/Library/Fonts/MarkerFelt.ttc"]
    path = next((f for f in fonts if os.path.exists(f)), None)
    big = ImageFont.truetype(path, 54) if path else ImageFont.load_default()
    small = ImageFont.truetype(path, 40) if path else ImageFont.load_default()
    ink = rnd.choice([(32, 44, 96), (28, 28, 34), (40, 60, 110)])
    dr.text((140, 70), f"{d.day} {d:%b %Y}", font=small, fill=ink)
    dr.text((140, 150 - 40), title, font=big, fill=ink)
    y = 170 + 56 - 46
    for line in textwrap.wrap(text, 36):
        dr.text((140 + rnd.randint(-4, 4), y), line, font=small, fill=ink); y += 56
    page = page.rotate(rnd.uniform(-3, 3), expand=True, fillcolor=(0, 0, 0, 0), resample=Image.BICUBIC)
    bg = Image.new("RGB", (page.width + 120, page.height + 120), rnd.choice([(92, 64, 44), (70, 74, 78), (120, 98, 76)]))
    shadow = Image.new("L", bg.size, 0); ImageDraw.Draw(shadow).rectangle([70, 76, 70 + page.width, 76 + page.height], fill=150)
    bg.paste((0, 0, 0), mask=shadow.filter(ImageFilter.GaussianBlur(14)))
    bg.paste(page, (60, 60), page.convert("L").point(lambda v: 255 if v > 8 else 0))
    bg.save(out, quality=86)


def dates(today):
    """Clusters on the same day across years, so On this day has something to show. Today gets two."""
    rnd, years, out = random.Random(7), range(today.year - 5, today.year + 1), []
    def ok(d): return d <= today
    md = (today.month, today.day)
    out += [today, today]
    for y in rnd.sample(list(years)[:-1], 3): out.append(date(y, *md))
    for _ in range(9):
        m, dd = rnd.randint(1, 12), rnd.randint(1, 28)
        for y in rnd.sample(list(years), rnd.randint(2, 3)):
            if ok(date(y, m, dd)): out.append(date(y, m, dd))
    start = date(today.year - 5, 1, 1)
    while len(out) < len(ENTRIES):
        d = start + timedelta(days=rnd.randint(0, (today - start).days))
        out.append(d)
    return out[:len(ENTRIES)]


def save(path, obj):
    with open(path, "w") as f: json.dump(obj, f, indent=1, ensure_ascii=False)


def add():
    remove(quiet=True)
    spec, meta = build.load_spec(), build.load_json(META, {"pages": {}, "cats": []})
    have = {c["id"] for c in meta["cats"]}
    meta["cats"] += [{"id": i, "name": n, "parent": p} for i, n, p in CATS if i not in have]
    rnd = random.Random(11)
    entries = ENTRIES[:]; rnd.shuffle(entries)
    for k, (d, (title, text, cats)) in enumerate(zip(dates(date.today()), entries), 1):
        pid = f"D{k:03d}"
        p = {"id": pid, "batch": "demo", "typed": True, "demo": True, "date_set": d.isoformat(), "title": title, "text": text, "type": "journal", "dates": [], "attachments": []}
        if k % 3 == 1:  # every third entry gets a photo of the handwritten page
            os.makedirs(f"{build.SRC}/attachments/{pid}", exist_ok=True)
            render_page(title, text, d, f"{build.SRC}/attachments/{pid}/page.jpg")
            p["attachments"] = [f"attachments/{pid}/page.jpg"]
        spec["pages"].append(p)
        meta["pages"][pid] = {"cats": cats, **({"star": True} if k % 5 == 0 else {})}
    save(SPEC, spec); save(META, meta); build.build()
    print(f"Added {len(ENTRIES)} sample entries in {len(CATS)} categories. Remove them with: python3 scripts/demo.py remove")


def remove(quiet=False):
    spec, meta = build.load_spec(), build.load_json(META, {"pages": {}, "cats": []})
    gone = {p["id"] for p in spec["pages"] if p.get("batch") == "demo"}
    spec["pages"] = [p for p in spec["pages"] if p["id"] not in gone]
    for pid in gone:
        meta["pages"].pop(pid, None)
        shutil.rmtree(f"{build.SRC}/attachments/{pid}", ignore_errors=True); shutil.rmtree(f"{build.OUT}/attachments/{pid}", ignore_errors=True)
    os.makedirs(build.SRC, exist_ok=True)
    save(SPEC, spec); save(META, meta)
    if not quiet: build.build(); print(f"Removed {len(gone)} demo entries.")


if __name__ == "__main__":
    {"add": add, "remove": remove}[sys.argv[1] if len(sys.argv) > 1 else "add"]()
