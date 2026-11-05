#!/usr/bin/env python3
"""
cf.py — Cloudflare Workers AI integratsiyasi (BEPUL: 10 000 neuron/kun).

Vazifalari:
  transcribe  — o'zbekcha nutqni matnga (Whisper large-v3-turbo)  ~17 s / audio
  flux        — rasm generatsiyasi (FLUX.1 schnell)  ~57 rasm/kun bepul
  llm         — transkriptdan kadr rejasi (Llama 3.1)

Ishlatish:
  export CF_TOKEN=v1.0-...
  python3 src/cf.py whoami
  python3 src/cf.py transcribe --audio build/narration.wav --out build/transcript.json
  python3 src/cf.py flux --prompt "pomegranate orchard at golden hour" --out assets/bg1.png
  python3 src/cf.py llm --transcript build/transcript.json --out scenes/hikoya.json
"""
import argparse
import base64
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://api.cloudflare.com/client/v4"
WHISPER = "@cf/openai/whisper-large-v3-turbo"
FLUX = "@cf/black-forest-labs/flux-1-schnell"
LLM = "@cf/meta/llama-3.1-8b-instruct"


def _tok():
    t = os.environ.get("CF_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if not t:
        sys.exit("CF_TOKEN o'rnatilmagan")
    return t


def api(path, data=None, raw=False, timeout=300):
    url = path if path.startswith("http") else BASE + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method="POST" if data else "GET", headers={
        "Authorization": f"Bearer {_tok()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            b = resp.read()
            return b if raw else json.loads(b)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        raise


_acct = None


def account_id():
    global _acct
    if _acct:
        return _acct
    if os.environ.get("CF_ACCOUNT_ID"):
        _acct = os.environ["CF_ACCOUNT_ID"]
        return _acct
    r = api("/accounts")
    if not r.get("result"):
        sys.exit("Account topilmadi — tokenda Workers AI ruxsati bormi?")
    _acct = r["result"][0]["id"]
    return _acct


# ----------------------------------------------------------------------------
def whoami():
    r = api("/accounts")
    for a in r.get("result", []):
        print("account:", a["id"], a["name"])
    return r


def transcribe(audio_path, language="uz"):
    """Whisper large-v3-turbo. 10 daqiqalik audio ≈ 2-3 daqiqa (bo'laklab yuboriladi)."""
    size = os.path.getsize(audio_path)
    if size > 9 * 1024 * 1024:
        raise SystemExit("Audio 9 MB dan katta — bo'laklarga ajratish kerak "
                         "(ffmpeg -f segment bilan).")
    b64 = base64.b64encode(open(audio_path, "rb").read()).decode()
    r = api(f"/accounts/{account_id()}/ai/run/{WHISPER}", {"audio": b64})
    res = r.get("result", {})
    text = res.get("text", "")
    segs = res.get("segments") or []
    out = []
    if segs:
        for s in segs:
            out.append({"start": round(float(s.get("start", 0)), 2),
                        "end": round(float(s.get("end", 0)), 2),
                        "text": s.get("text", "").strip(), "words": []})
    else:
        out = [{"start": 0.0, "end": 0.0, "text": text, "words": []}]
    return out, text


def flux(prompt, steps=6, width=1024, height=1024):
    r = api(f"/accounts/{account_id()}/ai/run/{FLUX}",
            {"prompt": prompt, "steps": steps})
    b64 = r["result"]["image"]
    return base64.b64decode(b64)


def llm(prompt, system=None, max_tokens=2048):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    r = api(f"/accounts/{account_id()}/ai/run/{LLM}",
            {"messages": msgs, "max_tokens": max_tokens})
    return r["result"]["response"]


PLANNER_SYSTEM = """Sen professional video rejissyorisan. Berilgan matnni 3-6 sekundlik
kadrlarga bo'lasan va har bir kadr uchun sahna tanlaysan.
FAQAT JSON qaytarasan, boshqa hech narsa yozma. Format:
{"shots": [{"text": "...", "dur": 4.0, "env": "orchard|orchard_dry|water",
            "cam": "wide|medium|close|detail|establishing",
            "move": "push_in|pan_lr|pull_out|orbit|tilt_up",
            "actor": "idle|walk|kneel|reach|none", "fruit": 0}]}
Qoidalar:
- matnni o'zgartirmasdan, aynan ko'chir
- bir xil kamera harakati ketma-ket takrorlanmasin
- anor/meva/bog' haqida gap ketsa env=orchard va fruit>0
- qiyinchilik/sinov/tanglik haqida gap ketsa env=orchard_dry
- odam haqida gap ketsa actor!=none
"""


def plan_from_transcript(text, max_words=1200):
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    out = llm(f"Matn:\n{text}\n\nKadr rejasini tuz.", system=PLANNER_SYSTEM)
    s = out[out.find("{"): out.rfind("}") + 1]
    return json.loads(s)


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami")

    p = sub.add_parser("transcribe")
    p.add_argument("--audio", required=True)
    p.add_argument("--out", default="build/transcript.json")
    p.add_argument("--lang", default="uz")

    p = sub.add_parser("flux")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", required=True)

    p = sub.add_parser("llm")
    p.add_argument("--transcript", required=True)
    p.add_argument("--out", default="scenes/hikoya.json")
    p.add_argument("--title", default="Video")

    a = ap.parse_args()

    if a.cmd == "whoami":
        whoami()

    elif a.cmd == "transcribe":
        segs, text = transcribe(a.audio, a.lang)
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(segs, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(text[:1500])
        print("\nTAYYOR:", a.out, len(segs), "segment")

    elif a.cmd == "flux":
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "wb").write(flux(a.prompt))
        print("TAYYOR:", a.out, os.path.getsize(a.out) // 1024, "KB")

    elif a.cmd == "llm":
        tr = json.load(open(a.transcript, encoding="utf-8"))
        text = " ".join(s["text"] for s in tr)
        p = plan_from_transcript(text)
        plan = {"title": a.title, "fps": 24, "res": [720, 1280],
                "shots": [{"id": i + 1, **s} for i, s in enumerate(p["shots"])]}
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(plan, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("TAYYOR:", a.out, len(plan["shots"]), "shot")


if __name__ == "__main__":
    main()
