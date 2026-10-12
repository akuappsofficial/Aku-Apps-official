#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"
python -m pip install -U -r requirements.txt
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg is optional; install it with: pkg install ffmpeg"
fi
echo "Open http://127.0.0.1:8080/mobile in your Android browser."
python yt.py --mobile --no-browser
