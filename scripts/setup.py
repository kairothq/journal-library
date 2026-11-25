"""One-command setup for your own copy. Run through ./setup.sh:
  ./setup.sh                    install, start the app on this Mac, open it in the browser
  ./setup.sh obsidian "<folder>"  pull notes from an Obsidian Daily logs folder (optional)
  ./setup.sh host <name>        put it online at https://<name>.pages.dev behind your password (optional)
  ./setup.sh stop               stop everything this script started"""
import json, os, plistlib, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.expanduser("~/Library/LaunchAgents")
LOGS = os.path.join(ROOT, "logs")
PATHS = ":".join([os.path.expanduser("~/.local/node/bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
UID = os.getuid()
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def say(*a): print(" ", *a, flush=True)
def stop_with(msg): print("\n  " + msg + "\n"); sys.exit(1)
def run(cmd, **kw): return subprocess.run(cmd, text=True, **kw)


def agent(name, args, **extra):
    """Write and (re)load a launchd agent so it starts at login and restarts if it stops."""
    label = f"com.journal-library.{name}"
    plist = {"Label": label, "ProgramArguments": args, "WorkingDirectory": ROOT, "RunAtLoad": True,
             "EnvironmentVariables": {"PATH": PATHS}, "StandardOutPath": f"{LOGS}/{name}.log", "StandardErrorPath": f"{LOGS}/{name}.error.log", **extra}
    path = os.path.join(AGENTS, label + ".plist")
    os.makedirs(AGENTS, exist_ok=True)
    run(["launchctl", "bootout", f"gui/{UID}/{label}"], capture_output=True)
    with open(path, "wb") as f: plistlib.dump(plist, f)
    r = run(["launchctl", "bootstrap", f"gui/{UID}", path], capture_output=True)
    if r.returncode: stop_with(f"Could not start {label}: {r.stderr.strip()}")
    return label


def install():
    if sys.platform != "darwin": stop_with("This needs a Mac: it reads your handwriting with macOS's built-in text recognition.")
    for tool, how in [("ffmpeg", "brew install ffmpeg"), ("swiftc", "xcode-select --install")]:
        if not shutil.which(tool, path=PATHS): stop_with(f"{tool} is missing. Install it with:  {how}   then run ./setup.sh again.")
    say("Installing Python packages (opencv, numpy)…")
    r = run([sys.executable, "-m", "pip", "install", "--user", "-q", "-r", os.path.join(ROOT, "requirements.txt")])
    if r.returncode: stop_with("pip could not install the packages above.")
    say("Building the text reader…")
    r = run(["swiftc", "-O", os.path.join(ROOT, "scripts", "ocr.swift"), "-o", os.path.join(ROOT, "scripts", "ocr")], capture_output=True)
    if r.returncode: stop_with("Could not build scripts/ocr.swift:\n" + r.stderr[-600:])
    for d in ("source", "logs", "out"): os.makedirs(os.path.join(ROOT, d), exist_ok=True)
    say("Starting the journal (it will start by itself whenever you log in)…")
    agent("server", [sys.executable, "scripts/server.py"], KeepAlive=True, ThrottleInterval=10)
    for _ in range(30):
        if run(["curl", "-s", "-o", "/dev/null", "http://127.0.0.1:8765/theme.js"]).returncode == 0: break
        time.sleep(1)
    print("\n  Done. Your journal: http://localhost:8765/add  (start by adding a video or photos of your pages)")
    print("  Optional next steps: ./setup.sh obsidian \"<folder>\"   and   ./setup.sh host <name>\n")
    run(["open", "http://localhost:8765/add"])


def obsidian(folder):
    import settings as cfg
    folder = os.path.expanduser(folder.rstrip("/"))
    if not os.path.isdir(folder): stop_with(f"Can't find the folder: {folder}")
    s = cfg.load(); s["obsidian"]["folder"] = folder; cfg.save(s)
    say("Saved the folder in Settings.")
    if "Mobile Documents" not in folder:
        say("The app checks it every 5 minutes. Done."); return
    # Background apps may not read iCloud folders, so a tiny helper app copies it into the journal.
    mirror = os.path.join(ROOT, "source", "obsidian_mirror")
    app = os.path.expanduser("~/Applications/JournalSync.app")
    script = (f'do shell script "/usr/bin/rsync -a --delete " & quoted form of "{folder}/" & " " & quoted form of "{mirror}/" & '
              '" && /usr/bin/curl -s -m 60 -X POST http://127.0.0.1:8765/api/obsidian/sync > /dev/null || true"')
    os.makedirs(os.path.dirname(app), exist_ok=True); shutil.rmtree(app, ignore_errors=True)
    r = run(["osacompile", "-o", app, "-e", script], capture_output=True)
    if r.returncode: stop_with("Could not build the sync helper: " + r.stderr)
    run(["/usr/libexec/PlistBuddy", "-c", "Add :LSUIElement bool true", f"{app}/Contents/Info.plist"], capture_output=True)
    run(["codesign", "--force", "--sign", "-", app], capture_output=True)
    agent("obsidian", [f"{app}/Contents/MacOS/applet"], WatchPaths=[folder], StartInterval=300)
    print("\n  macOS will ask once whether JournalSync may open files in iCloud Drive: click Allow.")
    print("  New notes now show up in the journal within a few seconds of syncing to this Mac.\n")


def host(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,56}", name or ""): stop_with("Pick a site name of lowercase letters, numbers and dashes, like  ./setup.sh host maya-journal")
    import settings as cfg
    if not cfg.load()["auth"]["hash"]:
        stop_with("Set a password first: open http://localhost:8765/settings > Password. The site stays locked without one.")
    if not shutil.which("cloudflared", path=PATHS): stop_with("cloudflared is missing. Install it with:  brew install cloudflared")
    if not shutil.which("npx", path=PATHS): stop_with("Node.js is missing. Install it with:  brew install node")
    dep = os.path.join(ROOT, "deploy")
    wr = ["npx", "-y", "wrangler@latest"]
    env = {**os.environ, "PATH": PATHS}
    if run(wr + ["whoami"], cwd=dep, env=env, capture_output=True).stdout.find("logged in") < 0:
        say("Log in to Cloudflare in the browser window that opens (a free account is enough)…")
        if run(wr + ["login"], cwd=dep, env=env).returncode: stop_with("Cloudflare login did not finish.")
    toml = os.path.join(dep, "wrangler.toml")
    if not os.path.exists(toml):
        say("Creating the storage that remembers where your Mac is…")
        out = run(wr + ["kv", "namespace", "create", f"{name}-tunnel"], cwd=dep, env=env, capture_output=True)
        m = re.search(r'id\s*[=:]\s*"?([0-9a-f]{32})', out.stdout + out.stderr)
        if not m: stop_with("Could not create the KV namespace:\n" + (out.stdout + out.stderr)[-600:])
        with open(os.path.join(dep, "wrangler.example.toml")) as f: t = f.read()
        with open(toml, "w") as f: f.write(t.replace("your-journal", name).replace("PASTE_KV_ID", m.group(1)))
    say(f"Publishing https://{name}.pages.dev …")
    run(wr + ["pages", "project", "create", name, "--production-branch", "main"], cwd=dep, env=env, capture_output=True)
    r = run(wr + ["pages", "deploy", "public", "--project-name", name, "--branch", "main", "--commit-dirty=true"], cwd=dep, env=env)
    if r.returncode: stop_with("Publishing failed (see above). If the name is taken, pick another one.")
    say("Starting the tunnel from this Mac…")
    agent("tunnel", [sys.executable, "scripts/tunnel.py"], KeepAlive=True, ThrottleInterval=30)
    print(f"\n  In a minute your journal is at https://{name}.pages.dev  (it works while this Mac is awake)\n")


def stop():
    for name in ("server", "tunnel", "obsidian"):
        label = f"com.journal-library.{name}"
        run(["launchctl", "bootout", f"gui/{UID}/{label}"], capture_output=True)
        p = os.path.join(AGENTS, label + ".plist")
        if os.path.exists(p): os.remove(p); say("stopped", label)
    print("  Your pages in source/ are untouched.\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: install()
    elif a[0] == "obsidian" and len(a) > 1: obsidian(a[1])
    elif a[0] == "host" and len(a) > 1: host(a[1])
    elif a[0] == "stop": stop()
    else: print(__doc__)
