#!/usr/bin/env python3
"""
plan_scenes.py — Transkriptdan KADR REJASI (storyboard) yasaydi.

Mantiq:
  1. Gaplarni 3-6 sekundlik "shot"larga bo'ladi
  2. Har bir shot matnidagi KALIT SO'ZLARGA qarab sahna/muhit tanlaydi
  3. Kamera harakatini navbat bilan almashtiradi (bir xil bo'lib qolmasin)
  4. scenes/<nom>.json faylini yozadi — uni qo'lda tahrirlash mumkin

Ishlatish:
  python3 src/plan_scenes.py --transcript build/transcript.json --out scenes/hikoya.json \
      --title "Sabr haqida" --total 60
"""
import argparse
import json
import math
import random
import re

# ---------------------------------------------------------------------------
# KALIT SO'Z → SAHNA XARITASI
# ---------------------------------------------------------------------------
RULES = [
    # (kalit so'zlar, muhit, kamera turi, qo'shimcha)
    (["anor", "meva", "hosil", "bog'", "bog‘", "daraxt", "ko'chat", "ko‘chat"],
     "orchard", "medium", {"fruit": 12}),
    (["qurg'oq", "qurg‘oq", "tang", "qiyinchilik", "sinov", "sabrsiz", "kut"],
     "orchard_dry", "wide", {"dry": True}),
    (["suv", "ariq", "daryo", "yomg'ir", "yomg‘ir", "buloq"],
     "water", "wide", {}),
    (["quyosh", "yorug'lik", "yorug‘lik", "tong", "subh", "nur"],
     "orchard", "wide", {"sun_energy": 4.0}),
    (["kech", "tun", "yulduz", "oy"],
     "night", "wide", {}),
    (["kitob", "qur'on", "qur’on", "oyat", "hadis", "ilm", "o'qi", "o‘qi"],
     "book", "close", {}),
    (["yurak", "qalb", "sabr", "shukr", "tavba"],
     "orchard", "close", {}),
    (["alloh", "robb", "bandalarim", "rahmat", "rizq"],
     "orchard", "establishing", {"sun_energy": 3.8}),
    (["odam", "inson", "u ", "uning", "yigit", "chol", "dehqon"],
     "orchard", "medium", {"actor": True}),
]

CAMS = ["push_in", "pan_lr", "pull_out", "orbit", "push_in", "tilt_up"]


def split_sentences(segments):
    """Whisper segmentlarini gaplarga bo'lish (tinish belgilari + pauzalar)."""
    text = " ".join(s["text"].strip() for s in segments)
    words = []
    for s in segments:
        for w in s["words"]:
            words.append(w)
    if not words:                                    # so'z vaqti yo'q bo'lsa
        return [{"text": s["text"].strip(), "start": s["start"], "end": s["end"]}
                for s in segments]

    # tinish belgisi bilan tugagan so'zlardan keyin gap chegarasi
    sentences, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end_punct = re.search(r"[.!?…:]$", w["w"].strip())
        long_pause = nxt and (nxt["s"] - w["e"]) > 0.65
        if end_punct or long_pause or nxt is None:
            txt = "".join(x["w"] if x["w"].startswith(" ") else " " + x["w"] for x in cur)
            sentences.append({"text": re.sub(r"\s+", " ", txt).strip(),
                              "start": cur[0]["s"], "end": cur[-1]["e"]})
            cur = []
    return sentences


def pick_visual(text, idx):
    low = text.lower()
    best, score = ("orchard", "medium", {}), 0
    for keys, env, cam, extra in RULES:
        s = sum(1 for k in keys if k in low)
        if s > score:
            best, score = (env, cam, dict(extra)), s
    return best


def build_plan(transcript, title="Video", fps=24, res=(720, 1280),
               min_dur=3.0, max_dur=6.0, start_offset=0.0, outro=1.6,
               actor=True):
    sentences = split_sentences(transcript)
    shots = []
    rnd = random.Random(7)

    buf, buf_start = [], None
    groups = []
    for s in sentences:
        if buf_start is None:
            buf_start = s["start"]
        buf.append(s)
        dur = buf[-1]["end"] - buf_start
        if dur >= min_dur:
            groups.append({"text": " ".join(x["text"] for x in buf),
                           "start": buf_start, "end": buf[-1]["end"]})
            buf, buf_start = [], None
    if buf:
        groups.append({"text": " ".join(x["text"] for x in buf),
                       "start": buf_start, "end": buf[-1]["end"]})

    cam_i = 0
    for g in groups:
        dur = max(min_dur, min(max_dur, g["end"] - g["start"]))
        env, camtype, extra = pick_visual(g["text"], len(shots))
        shot = {
            "id": len(shots) + 1,
            "dur": round(dur, 2),
            "text": g["text"],
            "env": env,
            "seed": rnd.randint(1, 999),
            "cam": {"type": camtype,
                    "move": CAMS[cam_i % len(CAMS)],
                    "azimuth": rnd.choice([88, 92, 96, 100, 76]),
                    "target": [0, 3.5, 1.2]},
            "dust": True,
        }
        cam_i += 1
        if extra.get("dry"):
            shot["dry"] = True
        if extra.get("fruit"):
            shot["trees"] = [
                {"pos": [0, 5.5, 0], "h": 3.6, "fruit": 16, "canopy": 1.1},
                {"pos": [-4.4, 8.0, 0], "h": 3.2, "fruit": 8},
                {"pos": [4.2, 7.4, 0], "h": 3.3, "fruit": 9},
            ]
            shot["cam"]["type"] = "detail"
            shot["cam"]["dist_scale"] = 3.4
            shot["cam"]["target"] = [0, 5.5, 2.4]
        if extra.get("sun_energy"):
            shot["sun_energy"] = extra["sun_energy"]
        if actor and env in ("orchard", "orchard_dry"):
            shot["actor"] = {"pose": rnd.choice(["idle", "walk", "idle", "reach"]),
                             "pos": [rnd.uniform(-0.8, 0.8), 3.8, 0],
                             "yaw": rnd.choice([180, 200, 160]),
                             "height": 1.78}
        shots.append(shot)

    if outro > 0:
        shots.append({"id": len(shots) + 1, "dur": outro, "text": "",
                      "env": "orchard", "seed": 999,
                      "cam": {"type": "establishing", "move": "pull_out",
                              "target": [0, 4, 1.6], "azimuth": 90},
                      "dust": True})

    return {"title": title, "fps": fps, "res": list(res), "shots": shots}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", default="scenes/hikoya.json")
    ap.add_argument("--title", default="Video")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--min-dur", type=float, default=3.0)
    ap.add_argument("--max-dur", type=float, default=6.0)
    ap.add_argument("--outro", type=float, default=1.6)
    a = ap.parse_args()

    tr = json.load(open(a.transcript, encoding="utf-8"))
    plan = build_plan(tr, title=a.title, fps=a.fps,
                      min_dur=a.min_dur, max_dur=a.max_dur, outro=a.outro)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    total = sum(s["dur"] for s in plan["shots"])
    print(f"TAYYOR: {a.out} — {len(plan['shots'])} shot, ~{total:.1f}s")
    for s in plan["shots"][:8]:
        print(f"  {s['dur']:4.1f}s [{s['env']:12s}] {s['text'][:60]}")
