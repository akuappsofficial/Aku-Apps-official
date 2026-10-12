# AKU Video Downloader — YT & Universal

A local Python downloader with a desktop web dashboard and a dedicated mobile interface. The mobile folder is included in the Windows package and its page can be opened on a PC too.

## Included files

- yt.py — Python local server, API, progress reporting, download queue and Test Mode.
- templates/index.html — desktop HTML interface.
- static/app.css and static/app.js — desktop design and controls.
- mobile/ — independent phone-first HTML, CSS, JavaScript and instructions.
- Windows launchers and START_TERMUX.sh for Android.
- GitHub Actions unit tests and Windows ZIP/executable packaging.

## Windows

Install Python 3.10+. Double-click START.bat for desktop or START_MOBILE.bat for mobile UI. Normally use http://127.0.0.1:8080/ or http://127.0.0.1:8080/mobile. The app prints LAN URLs for other devices on your trusted Wi-Fi. Do not expose this server to the public internet.

## Android / Termux

Run termux-setup-storage if you want shared storage access, then pkg install ffmpeg for MP3 support. Put this project folder on the phone and run bash START_TERMUX.sh in Termux. Open http://127.0.0.1:8080/mobile in the phone browser while Termux remains running.

## Selection and Test Mode

Select Best, 1080p, 720p, 480p, 360p, source audio, or MP3. Test Mode inspects the URL and metadata without downloading. Device diagnostics check Python, yt-dlp, FFmpeg, storage and internet. MP3 conversion requires FFmpeg; format availability depends on the source site.

## Resource safety

Maximum two active jobs; 64 KiB request body limit; 4096-character URL limit; per-job temporary folders; 2 GiB maximum file size; and a minimum 256 MiB free-storage check. Download only media you own or are authorized to save.

## Run tests

python -m unittest discover -s tests -v
