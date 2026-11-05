#!/usr/bin/env python3
"""
download.py — YouTube (yoki boshqa) havoladan faqat OVOZNI yuklab oladi.

Ishlatish:
  python3 src/download.py --url "https://youtube.com/watch?v=..." --out build/narration
"""
import argparse
import os
import subprocess
import sys


def download_audio(url, out_base="build/narration"):
    os.makedirs(os.path.dirname(out_base) or ".", exist_ok=True)
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--postprocessor-args", "-ar 16000 -ac 1",
        "-o", out_base + ".%(ext)s",
        "--no-playlist",
        url,
    ]
    print(" ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit("Yuklab olishda xato. Havolani tekshiring yoki `pip install -U yt-dlp` qiling.")
    path = out_base + ".wav"
    if not os.path.exists(path):
        sys.exit("WAV fayl yaratilmadi")
    print("TAYYOR:", path, os.path.getsize(path) // 1024, "KB")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="build/narration")
    a = ap.parse_args()
    download_audio(a.url, a.out)
