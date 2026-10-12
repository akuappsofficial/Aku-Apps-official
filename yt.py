#!/usr/bin/env python3
"""AKU Video Downloader: local desktop/mobile UI, Test Mode, and yt-dlp jobs."""
import json, mimetypes, os, platform, re, shutil, socket, sys, threading, time, uuid, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

try:
    import yt_dlp
except ImportError:
    raise SystemExit("Missing yt-dlp. Run: python -m pip install -r requirements.txt")

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PORT = int(os.environ.get("AKU_PORT", "8080"))
MAX_JOBS, MAX_BODY, MAX_FILE = 2, 65536, 2 * 1024**3
MIN_FREE = 256 * 1024**2
LOCK = threading.RLock()
JOBS = {}
ACTIVE = 0


def asset(*parts):
    return ROOT.joinpath(*parts)


def download_dir():
    home = Path.home()
    for p in (home/"storage/shared/Download/AKU-Video-Downloads",
              home/"Downloads/AKU-Video-Downloads", home/"AKU-Video-Downloads"):
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p/".write-test"
            test.write_text("ok", encoding="utf-8")
            test.unlink()
            return p
        except OSError:
            pass
    raise OSError("No writable download folder found.")


DEST = download_dir()


def normalize_url(value):
    value = str(value or "").strip()
    if not value:
        raise ValueError("Enter a URL or YouTube video ID.")
    if len(value) > 4096:
        raise ValueError("URL is too long (4096 characters maximum).")
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        value = "https://www.youtube.com/watch?v=" + value
    elif "://" not in value:
        value = "https://" + value
    p = urlparse(value)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise ValueError("Enter a valid http/https URL without embedded credentials.")
    return value


def fmt_bytes(n):
    if n is None:
        return "Unknown"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_duration(n):
    if n is None:
        return "Unknown"
    try:
        n = max(0, int(n))
    except (TypeError, ValueError):
        return "Unknown"
    h, rest = divmod(n, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def estimate(info, max_height=None, audio=False):
    best, duration = 0, info.get("duration") or 0
    for f in info.get("formats", []):
        vc, ac, h = f.get("vcodec"), f.get("acodec"), f.get("height")
        if audio:
            if ac in (None, "none") or vc not in (None, "none"):
                continue
        else:
            if vc in (None, "none") or (max_height is not None and h is not None and h > max_height):
                continue
        size = f.get("filesize") or f.get("filesize_approx")
        rate = f.get("abr" if audio else "tbr")
        if not size and rate and duration:
            size = int(float(rate) * 1000 / 8 * duration)
        best = max(best, int(size or 0))
    return best or None


def format_for(q):
    choices = {
        "best": ("bestvideo*+bestaudio/best", False),
        "1080p": ("bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", False),
        "720p": ("bestvideo[height<=720]+bestaudio/best[height<=720]/best", False),
        "480p": ("bestvideo[height<=480]+bestaudio/best[height<=480]/best", False),
        "360p": ("bestvideo[height<=360]+bestaudio/best[height<=360]/best", False),
        "audio": ("bestaudio/best", False),
        "mp3": ("bestaudio/best", True),
    }
    if q not in choices:
        raise ValueError("Unsupported quality selection.")
    return choices[q]


def analyze(url):
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True, "socket_timeout": 20, "retries": 2}) as ydl:
        info = ydl.extract_info(normalize_url(url), download=False)
    if not info:
        raise RuntimeError("No media information was returned.")
    return {
        "id": str(info.get("id") or ""), "title": str(info.get("title") or "Untitled"),
        "site": str(info.get("extractor_key") or info.get("extractor") or "Media"),
        "duration": fmt_duration(info.get("duration")), "uploader": str(info.get("uploader") or ""),
        "thumbnail": str(info.get("thumbnail") or ""), "filesize": fmt_bytes(estimate(info)),
        "filesize_720p": fmt_bytes(estimate(info, 720)),
        "formats": sorted({int(f["height"]) for f in info.get("formats", []) if f.get("height")}, reverse=True)[:12],
    }


def diagnostics(url=None):
    checks = [
        {"name": "Python", "ok": sys.version_info >= (3, 9), "detail": platform.python_version()},
        {"name": "yt-dlp", "ok": True, "detail": getattr(getattr(yt_dlp, "version", None), "__version__", "installed")},
    ]
    ffmpeg = shutil.which("ffmpeg")
    checks.append({"name": "FFmpeg", "ok": bool(ffmpeg), "detail": ffmpeg or "Not found; required for MP3 conversion"})
    try:
        free = shutil.disk_usage(DEST).free
        probe = DEST/".diagnostic"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append({"name": "Storage", "ok": free >= MIN_FREE, "detail": str(DEST) + " · " + fmt_bytes(free) + " free"})
    except OSError as e:
        checks.append({"name": "Storage", "ok": False, "detail": str(e)})
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=3):
            pass
        checks.append({"name": "Internet", "ok": True, "detail": "Connection succeeded"})
    except OSError:
        checks.append({"name": "Internet", "ok": False, "detail": "Connection test failed; check network/firewall"})
    result = {"checks": checks, "download_dir": str(DEST), "active_jobs": ACTIVE}
    if url:
        try:
            result["video"], result["url_ok"] = analyze(url), True
        except Exception as e:
            result["url_ok"], result["url_error"] = False, str(e)[:500]
    return result


def run_job(job_id, url, quality):
    global ACTIVE
    folder = DEST/".jobs"/job_id
    try:
        if shutil.disk_usage(DEST).free < MIN_FREE:
            raise OSError("Less than 256 MB of free storage is available.")
        folder.mkdir(parents=True, exist_ok=True)
        fmt, mp3 = format_for(quality)
        if mp3 and not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg is required for MP3 conversion. Install FFmpeg and retry.")
        def hook(d):
            with LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return
                if d.get("status") == "downloading":
                    got = d.get("downloaded_bytes") or 0
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    job.update(status="downloading", downloaded=got, total=total,
                               percent=round(min(100, got*100/total), 1) if total else None,
                               speed=d.get("_speed_str") or "", eta=d.get("_eta_str") or "")
                elif d.get("status") == "finished":
                    job.update(status="processing", percent=100, message="Finalizing media…")
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "format": fmt,
                "outtmpl": str(folder/"%(title).160B [%(id)s].%(ext)s"), "progress_hooks": [hook],
                "retries": 5, "fragment_retries": 5, "socket_timeout": 30, "continuedl": True,
                "overwrites": False, "max_filesize": MAX_FILE, "concurrent_fragment_downloads": 1}
        if mp3:
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        candidates = [p for p in folder.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not candidates:
            raise RuntimeError("Download finished without producing a file.")
        source = max(candidates, key=lambda p: p.stat().st_mtime)
        if source.stat().st_size > MAX_FILE:
            raise RuntimeError("Downloaded file exceeds the 2 GB safety limit.")
        target = DEST/source.name
        if target.exists():
            target = DEST/(source.stem+"-"+job_id[:6]+source.suffix)
        shutil.move(str(source), str(target))
        with LOCK:
            JOBS[job_id].update(status="completed", percent=100, title=str(info.get("title") or target.name),
                                filename=target.name, size=target.stat().st_size, message="Download complete.")
    except Exception as e:
        with LOCK:
            JOBS[job_id].update(status="error", error=str(e)[:700], message="Download failed.")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        with LOCK:
            ACTIVE = max(0, ACTIVE-1)


class Handler(BaseHTTPRequestHandler):
    server_version = "AKUVideo/2.1"
    def log_message(self, fmt, *args):
        print("[AKU] " + (fmt % args))
    def send_data(self, data, mime="application/json; charset=utf-8", status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def send_json(self, data, status=200):
        self.send_data(json.dumps(data, ensure_ascii=False).encode("utf-8"), status=status)
    def read_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > MAX_BODY:
                raise ValueError("Request is empty or exceeds 64 KiB.")
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Request JSON must be an object.")
            return data
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError("Invalid request body: " + str(e)) from e
    def serve_file(self, path):
        path = path.resolve()
        roots = [asset("templates").resolve(), asset("static").resolve(), asset("mobile").resolve()]
        if not any(p == path or p in path.parents for p in roots) or not path.is_file():
            return self.send_json({"error": "Not found"}, 404)
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_data(path.read_bytes(), mime + ("; charset=utf-8" if mime.startswith(("text/", "application/javascript")) else ""))
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self.serve_file(asset("templates", "index.html"))
        if path in ("/mobile", "/mobile/"):
            return self.serve_file(asset("mobile", "index.html"))
        if path.startswith("/static/"):
            return self.serve_file(asset("static", path[len("/static/"):]))
        if path.startswith("/mobile/"):
            return self.serve_file(asset("mobile", path[len("/mobile/"):]))
        if path == "/api/health":
            return self.send_json({"ok": True, "active_jobs": ACTIVE, "download_dir": str(DEST)})
        if path.startswith("/api/jobs/"):
            bits = path.strip("/").split("/")
            jid = bits[2] if len(bits) > 2 else ""
            with LOCK:
                job = JOBS.get(jid)
                if not job:
                    return self.send_json({"error": "Job not found"}, 404)
                snapshot = dict(job)
            if len(bits) > 3 and bits[3] == "file":
                if snapshot.get("status") != "completed":
                    return self.send_json({"error": "File is not ready."}, 409)
                file = DEST/snapshot.get("filename", "")
                if not file.is_file() or file.parent != DEST:
                    return self.send_json({"error": "File is no longer available."}, 404)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(file.stat().st_size))
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''"+quote(file.name))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    with file.open("rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            return self.send_json({k:v for k,v in snapshot.items() if k != "file_path"})
        return self.send_json({"error": "Not found"}, 404)
    def do_POST(self):
        global ACTIVE
        path = self.path.split("?", 1)[0]
        try:
            data = self.read_json()
            if path == "/api/info":
                return self.send_json({"ok": True, "video": analyze(data.get("url"))})
            if path == "/api/test":
                return self.send_json(diagnostics(normalize_url(data["url"]) if data.get("url") else None))
            if path == "/api/download":
                url, quality = normalize_url(data.get("url")), str(data.get("quality") or "best")
                format_for(quality)
                if shutil.disk_usage(DEST).free < MIN_FREE:
                    return self.send_json({"error": "Less than 256 MB free storage remains."}, 507)
                with LOCK:
                    if ACTIVE >= MAX_JOBS:
                        return self.send_json({"error": "Two downloads are already running. Try again shortly."}, 429)
                    jid = uuid.uuid4().hex[:12]
                    ACTIVE += 1
                    JOBS[jid] = {"id":jid,"status":"queued","percent":0,"downloaded":0,"total":None,"speed":"","eta":"","quality":quality,"created":time.time()}
                threading.Thread(target=run_job, args=(jid,url,quality), daemon=True).start()
                return self.send_json({"ok":True,"job_id":jid}, 202)
            return self.send_json({"error":"Not found"}, 404)
        except (ValueError, KeyError) as e:
            return self.send_json({"error":str(e)}, 400)
        except Exception as e:
            return self.send_json({"error":str(e)[:700]}, 500)


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("1.1.1.1", 443))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    global PORT
    mobile = "--mobile" in sys.argv
    open_browser = "--no-browser" not in sys.argv and platform.system() != "Android"
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            PORT = int(arg.split("=",1)[1])
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print("\nAKU VIDEO DOWNLOADER 2.1")
    print("Desktop UI : http://127.0.0.1:%s/" % PORT)
    print("Mobile UI  : http://127.0.0.1:%s/mobile" % PORT)
    print("LAN mobile : http://%s:%s/mobile" % (local_ip(), PORT))
    print("Downloads  : " + str(DEST))
    print("Test Mode is available in both interfaces. Ctrl+C stops the server.\n")
    if open_browser:
        url = "http://127.0.0.1:%s%s" % (PORT, "/mobile" if mobile else "/")
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping AKU Video Downloader…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
