# AKU Video Download - YT & Universal

CLI downloader plus a local-network browser dashboard, with a Windows executable build workflow.

## Windows
- Double-click `START.bat` to run the CLI and start the LAN dashboard.
- Double-click `START_WEB_SERVER.bat` to run only the dashboard.
- Double-click `BUILD_EXE.bat` to build an executable locally (requires Python and internet).

## Download the ZIP built by GitHub
Open the repository's **Actions** tab, select **Build AKU Video Downloader ZIP**, and download the artifact named `AKU_Video_Download_Windows` after the run succeeds. It contains the Windows executable and launcher files.

## Network use
Devices must be on the same Wi-Fi/hotspot. Open the URL printed in the terminal. Windows Firewall may ask for permission. The server limits active download jobs to two and streams files in 64 KiB chunks.

## Notes
- Requires internet for first-time dependency installation.
- The executable is built on GitHub's Windows runner.
- yt-dlp support varies by site. Download only media you own or are authorized to save.
- Audio selection downloads the available audio stream; MP3 transcoding is not bundled.
- This is a practical starting release; validate site compatibility and network behavior before broad deployment.
