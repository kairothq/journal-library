"""Keeps your pages.dev site pointed at this Mac.
Starts a Cloudflare quick tunnel to the journal on localhost:8765, then saves the tunnel's address in the
Pages site's KV so visits are forwarded here. Installed by ./setup.sh host, runs under launchd."""
import os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = os.environ.get("JOURNAL_PORT", "8765")
ENV = {**os.environ, "PATH": ":".join([os.path.expanduser("~/.local/node/bin"), "/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "/usr/bin:/bin")])}


def kv_id():
    with open(os.path.join(ROOT, "deploy", "wrangler.toml")) as f:
        return re.search(r'^id\s*=\s*"([0-9a-f]+)"', f.read(), re.M).group(1)


def publish(url):
    for attempt in range(5):
        r = subprocess.run(["npx", "-y", "wrangler@latest", "kv", "key", "put", "--namespace-id", kv_id(), "url", url, "--remote"],
                           cwd=os.path.join(ROOT, "deploy"), env=ENV, capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            print(time.strftime("%H:%M:%S"), "journal is live via", url, flush=True); return
        print("could not save the tunnel address:", r.stderr[-300:], flush=True); time.sleep(10 * (attempt + 1))


def main():
    p = subprocess.Popen(["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                         env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    done = False
    for line in p.stdout:
        if not done and (m := re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)):
            publish(m.group(0)); done = True
    sys.exit(p.wait())  # launchd restarts us, which makes a fresh tunnel


if __name__ == "__main__":
    main()
