#!/usr/bin/env python3
"""
transcribe.py — O'zbek tilidagi ma'ruzani matnga va SO'Z DARAJASIDAGI vaqtga aylantiradi.

Muhim: o'zbek tili uchun `large-v3` modeli kerak (`small` matnni buzadi).
4 yadro / 16 GB RAM (GitHub Actions) da 20 daqiqalik audio ≈ 6-10 daqiqa.

Ishlatish:
  python3 src/transcribe.py --audio build/narration.wav --out build/transcript.json
  python3 src/transcribe.py --audio a.wav --model large-v3 --language uz
"""
import argparse
import json
import os
import sys


def transcribe(audio, model_size="large-v3", language="uz", compute_type="int8"):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type=compute_type,
                         cpu_threads=os.cpu_count() or 4)
    segments, info = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 350},
        word_timestamps=True,
        condition_on_previous_text=False,
    )
    print(f"Til: {info.language} ({info.language_probability:.2f})", flush=True)

    out = []
    for s in segments:
        words = [{"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)}
                 for w in (s.words or [])]
        out.append({"start": round(s.start, 2), "end": round(s.end, 2),
                    "text": s.text.strip(), "words": words})
        print(f"[{s.start:7.2f} → {s.end:7.2f}] {s.text.strip()}", flush=True)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", default="build/transcript.json")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default="uz")
    a = ap.parse_args()
    segs = transcribe(a.audio, a.model, a.language)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(segs, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("TAYYOR:", a.out, len(segs), "segment")
