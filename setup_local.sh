#!/usr/bin/env bash
# setup_local.sh — lokal (CPU) muhitni tiklash. Idempotent: har sessiyada ishlatsa bo'ladi.
set -e
echo "[1/4] apt paketlar..."
if ! command -v blender >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq blender ffmpeg fonts-dejavu fontconfig >/dev/null 2>&1
fi
echo "  blender: $(blender --version 2>/dev/null | head -1)"
echo "  ffmpeg:  $(ffmpeg -version 2>/dev/null | head -1 | cut -c1-40)"

echo "[2/4] Python paketlar..."
python3 -c "import yt_dlp" 2>/dev/null || pip3 install -q yt-dlp
python3 -c "import faster_whisper" 2>/dev/null || pip3 install -q faster-whisper
python3 -c "import PIL" 2>/dev/null || pip3 install -q pillow numpy

echo "[3/4] Shriftlar..."
mkdir -p ~/anim/assets/fonts
for f in /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf; do
  [ -f "$f" ] && cp -n "$f" ~/anim/assets/fonts/ 2>/dev/null || true
done
ls ~/anim/assets/fonts 2>/dev/null | head -5

echo "[4/4] Rhubarb lip-sync..."
if [ ! -x ~/tools/Rhubarb-Lip-Sync-1.14.0-Linux/rhubarb ]; then
  mkdir -p ~/tools && cd ~/tools
  curl -sL -o rhubarb.zip "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-Linux.zip"
  unzip -oq rhubarb.zip && rm -f rhubarb.zip
fi
~/tools/Rhubarb-Lip-Sync-1.14.0-Linux/rhubarb --version 2>&1 | head -1 || echo "  (rhubarb yo'q — lip-sync keyinroq)"
echo "TAYYOR."
