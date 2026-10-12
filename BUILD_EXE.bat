@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python -m pip install -r requirements.txt pyinstaller && python -m PyInstaller --onefile --console --name "AKU Video Downloader" --collect-all yt_dlp yt.py) else (py -3 -m pip install -r requirements.txt pyinstaller && py -3 -m PyInstaller --onefile --console --name "AKU Video Downloader" --collect-all yt_dlp yt.py)
pause
