# 🎬 Anim Studio — ma'ruzadan 3D animatsion video

Abdulloh domla (yoki boshqa) ma'ruzalarining **ovozidan** to'liq **3D animatsion video** yasaydigan
tizim. Har bir gap uchun mos sahna chiziladi: odam, daraxtlar, quyosh, osmon, chang zarralari —
hammasi Blender'da kod bilan quriladi (tashqi 3D model kerak emas).

Format: **9:16 vertikal (720×1280)**, 24 fps, YouTube Shorts / Reels / TikTok uchun.

---

## 1. Tez boshlash

```bash
# 0) Muhitni tiklash (har yangi sessiyada)
bash setup_local.sh

# 1) YouTube'dan ovozni olish
python3 src/download.py --url "https://youtube.com/watch?v=XXXX" --out build/narration

# 2) Matnga + vaqtga aylantirish  (o'zbek uchun large-v3 SHART)
python3 src/transcribe.py --audio build/narration.wav --out build/transcript.json --model large-v3

# 3) Kadr rejasini yasash (storyboard)
python3 src/plan_scenes.py --transcript build/transcript.json --out scenes/hikoya.json \
        --title "Sabr haqida"

# 4) GitHub'ga yuborish → Actions o'zi render qiladi → Telegram'ga tushadi
python3 src/gh.py push --repo anim-studio --msg "hikoya"
python3 src/gh.py run  --repo anim-studio --plan scenes/hikoya.json --samples 48
```

---

## 2. Arxitektura

```
 YouTube link
     │  src/download.py  (yt-dlp)
     ▼
 narration.wav
     │  src/transcribe.py  (faster-whisper large-v3, so'z darajasida vaqt)
     ▼
 transcript.json
     │  src/plan_scenes.py  (kalit so'z → sahna; gap → shot)
     ▼
 scenes/hikoya.json  ◄──── qo'lda tahrirlash mumkin (har bir kadrni boshqarish)
     │
     │  git push
     ▼
 GitHub Actions
     ├── job: plan
     ├── job×N: render  →  blender -b build_scene.py  →  clip_XX.mp4   (parallel!)
     └── job: compose   →  src/compose.py (xfade + grade + subtitr + audio)
                              └── Telegram bot → telefonda video
```

Webhook va server kerak emas — hammasi bepul GitHub runner'larida ishlaydi.

---

## 3. Fayllar

| Fayl | Vazifasi |
|---|---|
| `blender/lib_style.py` | Palitra, gradient osmon, quyosh nuri, materiallar, bloom/mist, GPU sozlash |
| `blender/lib_nature.py` | Procedural daraxt (anor + shox + barg + meva), o't, tepalik, bulut, quyosh diski |
| `blender/lib_character.py` | Sallali oq jellyali odam + skelet (idle / walk / kneel / reach) |
| `blender/lib_camera.py` | Kamerа turlari (wide…detail) va harakatlari (push-in, pan, orbit, tilt) |
| `blender/lib_fx.py` | Havodagi chang, tushayotgan barg, yorug'lik ustuni |
| `blender/build_scene.py` | Plan JSON'dan bitta kadrni qurib render qiladi |
| `src/download.py` | YouTube'dan faqat ovoz |
| `src/transcribe.py` | Whisper transkripsiya (o'zbek, so'z vaqtlari bilan) |
| `src/plan_scenes.py` | Transkript → kadr rejasi |
| `src/compose.py` | xfade o'tishlar, rang, subtitr (ASS), audio, watermark |
| `src/gh.py` | Repo yaratish / push / secret / workflow / artefakt / Telegram |
| `.github/workflows/render.yml` | Parallel render farm + montaj + Telegram |
| `setup_local.sh` | Lokal muhitni tiklash (blender, ffmpeg, whisper) |

---

## 4. Kadr rejasi (`scenes/*.json`)

```json
{
  "title": "Sabr haqida",
  "fps": 24,
  "res": [720, 1280],
  "shots": [
    {
      "id": 1,
      "dur": 4.5,
      "text": "Har bir berilmagan narsani mahrumlik deb hisoblama.",
      "env": "orchard",
      "seed": 11,
      "actor": { "pose": "walk", "pos": [-2.6, 2.6, 0], "yaw": 180 },
      "cam": { "type": "wide", "move": "push_in", "target": [0, 2.2, 0], "azimuth": 90 },
      "dust": true
    }
  ]
}
```

### `env` — muhit
| qiymat | tavsif |
|---|---|
| `orchard` | yashil mevali bog' |
| `orchard_dry` | qurigan bog', yorilgan yer |
| `water` | suv/ariq |

### `actor.pose`
`idle` (nafas oladi) · `walk` · `kneel` (tiz cho'kadi) · `reach` (meva uzadi)

### `cam.type`
`establishing` · `wide` · `medium` · `close` · `closeup` · `detail` · `low` · `high`

### `cam.move`
`push_in` (sekin yaqinlashish — referensdagi asosiy harakat) · `pull_out` · `pan_lr` · `pan_rl`
· `orbit` · `tilt_up` · `handheld` · `static`

### Boshqa maydonlar
`trees` — daraxtlarni qo'lda joylashtirish · `sun_energy` · `sky_top` / `sky_horizon` (rang)
· `dry` · `grass`, `far_trees`, `clouds`, `dust_count` — zichlik · `seed` — takrorlanuvchanlik

---

## 5. Vaqt va xarajat

| Bosqich | Vaqt (60 sek video) |
|---|---|
| Transkripsiya (large-v3, 4 yadro) | ~4–6 daqiqa |
| Render (6 shot, parallel) | ~8–12 daqiqa |
| Montaj | ~1 daqiqa |
| **Jami** | **~15 daqiqa** |

GitHub Actions: public repo — **cheksiz bepul**; private — oyiga 2000 daqiqa (bizga ~40 ta video yetadi).

---

## 6. Uslubni o'zgartirish

`blender/lib_style.py` → `PALETTE` lug'ati:

```python
"sky_top":     (0.055, 0.170, 0.190),   # osmon tepasi (to'q feruza)
"sky_horizon": (0.980, 0.760, 0.420),   # ufq (oltin)
"leaf_a":      (0.130, 0.290, 0.150),   # barg (soya)
"fruit":       (0.640, 0.075, 0.090),   # anor qizil
```

Rangni o'zgartirsangiz butun video ohangi o'zgaradi.

---

## 7. Muammolar

| Muammo | Yechim |
|---|---|
| Whisper o'zbekchani buzadi | `--model large-v3` ishlating (`medium` ham yetarli emas) |
| Render juda sekin | `--samples 16 --quality 0.5` bilan sinov, keyin to'liq |
| `Killed` / OOM | Lokal 2 GB RAMga sig'maydi — GitHub Actions'da ishlating |
| YouTube yuklanmaydi | `pip install -U yt-dlp`; ba'zi videolar login talab qiladi |
| Artefakt juda katta | render job darhol mp4'ga kodlaydi (PNG emas) — 500 MB limitiga sig'adi |

---

## 8. Yo'l xaritasi

- [x] 3D sahna generatori (daraxt, odam, quyosh, kamera, FX)
- [x] Parallel render farm (GitHub Actions)
- [x] Montaj: o'tishlar, grade, subtitr, watermark
- [x] Telegram'ga yetkazish
- [ ] **Lip-sync** — odam gapirganda og'zi qimirlashi (Rhubarb + blend shape)
- [ ] Harfma-harf subtitr (karaoke effekti)
- [ ] Fon musiqasi (litsenziyasiz ambient pad generatsiyasi)
- [ ] 1080×1920 versiyasi
- [ ] Qahramonning yuz ifodasi (tabassum, xafa)
