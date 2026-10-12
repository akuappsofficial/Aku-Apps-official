@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --console --name "AKU Video Downloader" --collect-all yt_dlp --add-data "templates;templates" --add-data "static;static" --add-data "mobile;mobile" yt.py
pause
