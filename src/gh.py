#!/usr/bin/env python3
"""
gh.py — GitHub bilan ishlash: repo yaratish, push, secret qo'yish, workflow ishga tushirish,
artefaktni yuklab olib Telegram'ga yuborish.

Ishlatish:
  export GH_TOKEN=github_pat_xxx
  python3 src/gh.py create   --repo anim-studio --public
  python3 src/gh.py push     --repo anim-studio --msg "birinchi versiya"
  python3 src/gh.py secrets  --repo anim-studio --tg-token ... --tg-chat ... --watermark "nom.uz"
  python3 src/gh.py run      --repo anim-studio --plan scenes/demo.json --samples 48
  python3 src/gh.py watch    --repo anim-studio
  python3 src/gh.py telegram --chat 7179261501 --file final.mp4 --caption "Tayyor"
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

API = "https://api.github.com"


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not t:
        sys.exit("GH_TOKEN o'rnatilmagan")
    return t


def req(method, path, data=None, raw=False, ctype="application/json"):
    url = path if path.startswith("http") else API + path
    body = None
    headers = {
        "Authorization": f"Bearer {token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "anim-studio",
    }
    if data is not None:
        body = json.dumps(data).encode() if ctype == "application/json" else data
        headers["Content-Type"] = ctype
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            b = resp.read()
            return b if raw else (json.loads(b) if b else {})
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}", file=sys.stderr)
        raise


def me():
    return req("GET", "/user")["login"]


def repo_exists(full):
    try:
        req("GET", f"/repos/{full}")
        return True
    except urllib.error.HTTPError:
        return False


def cmd_create(a):
    user = me()
    full = f"{user}/{a.repo}"
    if repo_exists(full):
        print("Repo allaqachon bor:", full)
        return
    r = req("POST", "/user/repos", {
        "name": a.repo,
        "description": "3D animatsion video pipeline (Blender + ffmpeg)",
        "private": not a.public,
        "auto_init": False,
        "has_issues": False,
        "has_wiki": False,
    })
    print("Yaratildi:", r["html_url"])


def cmd_push(a):
    user = me()
    full = f"{user}/{a.repo}"
    url = f"https://x-access-token:{token()}@github.com/{full}.git"
    run = lambda c: subprocess.run(c, shell=True, cwd=os.getcwd())

    if not os.path.isdir(".git"):
        run("git init -q && git checkout -q -b main")
    run('git config user.email "bot@anim.studio" && git config user.name "anim-bot"')
    run("git add -A")
    run(f'git commit -q -m "{a.msg}" || echo "(o\'zgarish yo\'q)"')
    run(f"git remote remove origin 2>/dev/null; git remote add origin {url}")
    r = run("git push -u origin main --force 2>&1 | tail -3")
    if r.returncode != 0:
        sys.exit("Push muvaffaqiyatsiz")
    # tokenni .git/config dan olib tashlash
    run(f"git remote set-url origin https://github.com/{full}.git")
    print("Push OK:", f"https://github.com/{full}")


def cmd_secrets(a):
    from nacl import encoding, public
    user = me()
    full = f"{user}/{a.repo}"
    key = req("GET", f"/repos/{full}/actions/secrets/public-key")

    def put(name, value):
        pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pk).encrypt(value.encode())
        req("PUT", f"/repos/{full}/actions/secrets/{name}",
            {"encrypted_value": base64.b64encode(sealed).decode(),
             "key_id": key["key_id"]})
        print("  secret:", name)

    if a.tg_token:
        put("TG_BOT_TOKEN", a.tg_token)
    if a.tg_chat:
        put("TG_CHAT_ID", str(a.tg_chat))
    if a.watermark:
        put("WATERMARK", a.watermark)
    if a.narration_url:
        put("NARRATION_URL", a.narration_url)


def cmd_run(a):
    user = me()
    full = f"{user}/{a.repo}"
    req("POST", f"/repos/{full}/actions/workflows/render.yml/dispatches", {
        "ref": "main",
        "inputs": {"plan": a.plan, "samples": str(a.samples),
                   "quality": str(a.quality)},
    })
    print("Workflow ishga tushirildi:", f"https://github.com/{full}/actions")


def cmd_watch(a):
    user = me()
    full = f"{user}/{a.repo}"
    print("Kuzatilmoqda:", full)
    last = None
    for _ in range(400):
        runs = req("GET", f"/repos/{full}/actions/runs?per_page=1")["workflow_runs"]
        if not runs:
            time.sleep(8)
            continue
        r = runs[0]
        st = f'{r["status"]}/{r["conclusion"]}'
        if st != last:
            print(" ", st, r["html_url"])
            last = st
        if r["status"] == "completed":
            return r["conclusion"]
        time.sleep(10)
    return "timeout"


def cmd_download(a):
    user = me()
    full = f"{user}/{a.repo}"
    runs = req("GET", f"/repos/{full}/actions/runs?per_page=1")["workflow_runs"]
    run_id = runs[0]["id"]
    arts = req("GET", f"/repos/{full}/actions/runs/{run_id}/artifacts")["artifacts"]
    name = a.artifact or "final-video"
    match = next((x for x in arts if x["name"] == name), None)
    if not match:
        sys.exit(f"Artefakt topilmadi: {name}. Mavjud: {[x['name'] for x in arts]}")
    data = req("GET", match["archive_download_url"], raw=True)
    with open("artifact.zip", "wb") as f:
        f.write(data)
    subprocess.run("unzip -o -q artifact.zip && rm artifact.zip", shell=True)
    print("Yuklandi:", match["name"])


def cmd_telegram(a):
    f = a.file
    if not os.path.exists(f):
        sys.exit("Fayl topilmadi: " + f)
    boundary = "----animstudio"
    fields = {"chat_id": str(a.chat), "caption": a.caption,
              "supports_streaming": "true", "width": "720", "height": "1280"}
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n")
    body = "".join(parts).encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; "
             f"filename=\"{os.path.basename(f)}\"\r\nContent-Type: video/mp4\r\n\r\n").encode()
    body += open(f, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{a.bot_token}/sendVideo"
    r = urllib.request.Request(url, data=body, method="POST",
                               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(r, timeout=300) as resp:
        print(resp.read().decode()[:300])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create"); p.add_argument("--repo", required=True)
    p.add_argument("--public", action="store_true"); p.set_defaults(f=cmd_create)

    p = sub.add_parser("push"); p.add_argument("--repo", required=True)
    p.add_argument("--msg", default="update"); p.set_defaults(f=cmd_push)

    p = sub.add_parser("secrets"); p.add_argument("--repo", required=True)
    p.add_argument("--tg-token"); p.add_argument("--tg-chat")
    p.add_argument("--watermark"); p.add_argument("--narration-url")
    p.set_defaults(f=cmd_secrets)

    p = sub.add_parser("run"); p.add_argument("--repo", required=True)
    p.add_argument("--plan", default="scenes/demo.json")
    p.add_argument("--samples", default=48); p.add_argument("--quality", default=1.0)
    p.set_defaults(f=cmd_run)

    p = sub.add_parser("watch"); p.add_argument("--repo", required=True)
    p.set_defaults(f=cmd_watch)

    p = sub.add_parser("download"); p.add_argument("--repo", required=True)
    p.add_argument("--artifact", default="final-video"); p.set_defaults(f=cmd_download)

    p = sub.add_parser("telegram"); p.add_argument("--bot-token", required=True)
    p.add_argument("--chat", required=True); p.add_argument("--file", required=True)
    p.add_argument("--caption", default=""); p.set_defaults(f=cmd_telegram)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
