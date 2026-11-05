#!/usr/bin/env python3
"""
compose.py — Shot kliplarini bitta videoga yig'adi:
  o'tishlar (xfade) + rang berish (grade) + subtitrlar (ASS) + audio + Telegram uchun tayyor mp4.

Ishlatish:
  python3 src/compose.py --plan scenes/demo.json --clips-dir . --out final.mp4 --audio narration.m4a
"""
import argparse
import json
import os
import subprocess
import sys

TRANSITION = 0.55          # shotlar orasidagi o'tish (soniya)
FONT = "DejaVu Sans"


# ----------------------------------------------------------------------------
# ASS SUBTITR
# ----------------------------------------------------------------------------
def ts(t):
    """ASS vaqt formati: H:MM:SS.cc"""
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(plan, path, res=(720, 1280), watermark=""):
    W, H = res
    fs_title = int(H * 0.030)      # subtitr shrifti
    fs_wm = int(H * 0.016)
    margin_v = int(H * 0.145)      # pastdan masofa
    outline = max(2, int(H * 0.0035))

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},{fs_title},&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,-1,0,0,0,100,100,0.6,0,1,{outline},1.2,2,{int(W*0.07)},{int(W*0.07)},{margin_v},1
Style: WM,{FONT},{fs_wm},&H60C8C8C8,&H60C8C8C8,&H00000000,&H00000000,0,0,0,0,100,100,1.2,0,1,0,0,2,{int(W*0.07)},{int(W*0.07)},{int(H*0.088)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    T = TRANSITION
    t = 0.0
    events = []
    for i, shot in enumerate(plan["shots"]):
        d = float(shot["dur"])
        start = t
        end = t + d
        text = shot.get("text", "").strip()
        if text:
            s = start + (T * 0.5 if i > 0 else 0.15)
            e = end - (T * 0.5 if i < len(plan["shots"]) - 1 else 0.35)
            if e > s:
                events.append(
                    f"Dialogue: 1,{ts(s)},{ts(e)},Sub,,0,0,0,,{{\\fad(220,220)}}{text}")
        t = end - T
    if watermark:
        total = t + T
        events.append(
            f"Dialogue: 0,0:00:00.30,{ts(total)},WM,,0,0,0,,{{\\fad(400,400)}}{watermark}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
    return path


# ----------------------------------------------------------------------------
# FFMPEG MONTAJ
# ----------------------------------------------------------------------------
def compose(plan, clips_dir, out, audio=None, watermark="", crf=20, bloom=0.16):
    shots = plan["shots"]
    fps = plan.get("fps", 24)
    res = plan.get("res", [720, 1280])
    T = TRANSITION

    clips = []
    for i in range(len(shots)):
        c = os.path.join(clips_dir, f"clip_{i}.mp4")
        if not os.path.exists(c):
            sys.exit(f"XATO: {c} topilmadi")
        clips.append(c)

    ass = os.path.join(os.path.dirname(out) or ".", "subs.ass")
    build_ass(plan, ass, res=tuple(res), watermark=watermark)

    total = sum(float(s["dur"]) for s in shots) - T * (len(shots) - 1)

    inputs, fc = [], []
    for c in clips:
        inputs += ["-i", c]

    # 1) o'tishlar
    if len(clips) == 1:
        fc.append("[0:v]null[vx]")
    else:
        prev = "[0:v]"
        t = 0.0
        for i in range(1, len(clips)):
            t += float(shots[i - 1]["dur"]) - T
            lbl = f"[v{i}]"
            fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={T}:offset={t:.3f}{lbl}")
            prev = lbl
        fc.append(f"{prev}null[vx]")

    # 2) rang / atmosfera: bloom + kontrast + vignette + grain + subtitr
    fc.append(
        f"[vx]split=2[base][blr];"
        f"[blr]gblur=sigma=20,eq=brightness=0.04[glow];"
        f"[base][glow]blend=all_mode=screen:all_opacity={bloom}[lit];"
        f"[lit]eq=contrast=1.05:saturation=1.07:gamma=0.99,"
        f"vignette=angle=PI/5,"
        f"noise=alls=4:allf=t+u,"
        f"ass={ass}[vout]"
    )

    # 3) audio
    if audio and os.path.exists(audio):
        inputs += ["-i", audio]
        ai = len(clips)
        fc.append(
            f"[{ai}:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
            f"loudnorm=I=-16:TP=-1.5:LRA=11,"
            f"afade=t=out:st={max(0, total-1.2):.2f}:d=1.2[aout]"
        )
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    else:
        fc.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[aout]")
        amap = ["-map", "[aout]", "-c:a", "aac", "-b:a", "96k"]

    cmd = (["ffmpeg", "-y", "-v", "warning"] + inputs +
           ["-filter_complex", ";".join(fc),
            "-map", "[vout]"] + amap +
           ["-t", f"{total:.3f}", "-r", str(fps),
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    print(" ".join(cmd)[:400], "...")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("ffmpeg xato bilan tugadi")
    print("TAYYOR:", out, f"({total:.1f}s)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--clips-dir", default=".")
    ap.add_argument("--out", default="final.mp4")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--watermark", default="")
    ap.add_argument("--crf", type=int, default=20)
    a = ap.parse_args()
    plan = json.load(open(a.plan, encoding="utf-8"))
    compose(plan, a.clips_dir, a.out, a.audio, a.watermark, a.crf)


if __name__ == "__main__":
    main()
