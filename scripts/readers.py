"""Optional page readers that replace macOS Vision's text and dates. Chosen in Settings.
  ollama     a vision model running on this Mac (nothing leaves the machine)
  anthropic  Claude API with your key
  bedrock    Amazon Bedrock with a short-term API key
Each returns {"text": str, "title": str, "dates": ["YYYY-MM-DD", ...]} or raises."""
import base64, json, os, re, subprocess, tempfile, urllib.request

PROMPT = """This is a photo of one handwritten journal page. Writing may be in any language, or mix languages.
Return ONLY JSON: {{"title": first line or heading, "text": the full page transcribed line by line, "dates": [every date written on the page as the date of an entry, as YYYY-MM-DD]}}.
Ignore deadlines like "by 1 Jan". If a date has no year, use {year}. Never invent a date that is not written."""


def _img(path, side=1568):
    import cv2
    im = cv2.imread(path); h, w = im.shape[:2]; s = min(1, side / max(h, w))
    if s < 1: im = cv2.resize(im, (int(w * s), int(h * s)))
    return base64.b64encode(cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()).decode()


def _json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m: raise ValueError("The model did not return JSON")
    d = json.loads(m.group(0))
    dates = [x for x in d.get("dates") or [] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(x))]
    return {"text": str(d.get("text") or "").strip(), "title": str(d.get("title") or "").strip()[:60], "dates": dates}


def _post(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read())


def read(cfg, path, year):
    p, prompt = cfg["provider"], PROMPT.format(year=year)
    if p == "ollama":
        r = _post(cfg["ollama_url"].rstrip("/") + "/api/generate", {"model": cfg["ollama_model"], "prompt": prompt, "images": [_img(path, 1280)],
                  "stream": False, "format": "json", "options": {"temperature": 0}}, {})
        return _json(r.get("response", ""))
    if p == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages", {"model": cfg["anthropic_model"], "max_tokens": 2000, "messages": [{"role": "user", "content": [
                  {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _img(path)}}, {"type": "text", "text": prompt}]}]},
                  {"x-api-key": cfg["anthropic_key"], "anthropic-version": "2023-06-01"})
        return _json("".join(b.get("text", "") for b in r.get("content", [])))
    if p == "bedrock":
        req = {"modelId": cfg["bedrock_model"], "messages": [{"role": "user", "content": [{"image": {"format": "jpeg", "source": {"bytes": _img(path)}}}, {"text": prompt}]}],
               "inferenceConfig": {"maxTokens": 2000, "temperature": 0}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f: json.dump(req, f); jp = f.name
        try:
            r = subprocess.run(["aws", "bedrock-runtime", "converse", "--region", "us-east-1", "--cli-input-json", f"file://{jp}", "--output", "json"],
                               capture_output=True, text=True, env={**os.environ, "AWS_BEARER_TOKEN_BEDROCK": cfg["bedrock_key"]}, timeout=180)
        finally:
            os.unlink(jp)
        if r.returncode: raise RuntimeError(r.stderr.strip()[-200:])
        return _json(json.loads(r.stdout)["output"]["message"]["content"][0].get("text", ""))
    raise ValueError("macOS Vision is built in")


def test(cfg):
    """Cheap check that the chosen reader is reachable and the model exists."""
    p = cfg["provider"]
    if p == "vision": return "macOS Vision is built in and ready."
    if p == "ollama":
        with urllib.request.urlopen(cfg["ollama_url"].rstrip("/") + "/api/tags", timeout=5) as r: models = [m["name"] for m in json.loads(r.read()).get("models", [])]
        if not any(m.split(":")[0] == cfg["ollama_model"].split(":")[0] for m in models):
            return f"Ollama is running but {cfg['ollama_model']} isn't downloaded. Run: ollama pull {cfg['ollama_model']}"
        return f"Ollama is running with {cfg['ollama_model']}."
    if p == "anthropic":
        if not cfg["anthropic_key"]: raise ValueError("Add your Claude API key first.")
        _post("https://api.anthropic.com/v1/messages", {"model": cfg["anthropic_model"], "max_tokens": 5, "messages": [{"role": "user", "content": "Say ok"}]},
              {"x-api-key": cfg["anthropic_key"], "anthropic-version": "2023-06-01"}, timeout=30)
        return f"Claude API key works with {cfg['anthropic_model']}."
    if p == "bedrock":
        if not cfg["bedrock_key"]: raise ValueError("Add your Bedrock API key first.")
        return "Bedrock key saved. It is checked on the next upload."
    raise ValueError("Unknown reader")
