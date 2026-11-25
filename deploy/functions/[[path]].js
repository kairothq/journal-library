// Forwards every visit to the journal running on your Mac, through a Cloudflare quick tunnel.
// The Mac writes its current tunnel address into KV each time the tunnel starts.
const OFFLINE = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Journal</title><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#1a120d;color:#efe3cf;font:16px/1.5 system-ui;text-align:center;padding:24px">
<div><h1 style="font:400 34px Georgia,serif;margin:0 0 8px">The journal is asleep</h1><p style="color:#a8957d;margin:0">It lives on the Mac. Open the laptop and this page will work again in a minute.</p></div>`;

export async function onRequest({ request, env }) {
  const target = await env.TUNNEL.get("url");
  const offline = () => new Response(OFFLINE, { status: 503, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
  if (!target) return offline();
  const url = new URL(request.url), to = new URL(target);
  url.protocol = to.protocol; url.host = to.host; url.port = "";
  try {
    const res = await fetch(new Request(url, request), { redirect: "manual" });
    if ([502, 503, 504, 530].includes(res.status)) return offline();
    const out = new Response(res.body, res);
    out.headers.set("cache-control", "no-store");
    out.headers.set("x-robots-tag", "noindex, nofollow");
    return out;
  } catch {
    return offline();
  }
}
