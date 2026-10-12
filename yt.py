#!/usr/bin/env python3
"""AKU Video Download - YT & Universal. CLI + LAN dashboard."""
import os, sys, time, threading, socket, tempfile, shutil, html, re
from urllib.parse import parse_qs, urlparse, quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import yt_dlp
except ImportError:
    print("Missing dependency: yt-dlp. Run: python -m pip install -r requirements.txt")
    raise SystemExit(1)

PORT = int(os.environ.get("AKU_PORT", "8080"))
MAX_JOBS = threading.BoundedSemaphore(2)
JOBS_LOCK = threading.Lock()
JOBS = set()

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except OSError: return "127.0.0.1"
    finally: s.close()

def fmt_bytes(n):
    if n is None: return "Unknown"
    n = float(n)
    for unit in ("B","KB","MB","GB","TB"):
        if n < 1024: return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def estimate(info, max_height=None):
    duration = info.get("duration") or 0
    best = 0
    for f in info.get("formats", []):
        if f.get("vcodec") in (None, "none"): continue
        h = f.get("height")
        if max_height and h and h > max_height: continue
        size = f.get("filesize") or f.get("filesize_approx")
        if not size and f.get("tbr") and duration:
            size = int(f["tbr"] * 1000 / 8 * duration)
        best = max(best, size or 0)
    return best or None

def expand_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname: raise ValueError("Enter a valid http/https URL.")
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r: return r.geturl()
    except Exception: return url

def analyze(url):
    opts = {"quiet":True, "no_warnings":True, "noplaylist":True}
    with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(expand_url(url), download=False)

def page(body):
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>AKU Video Download</title><style>*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#080d18;color:#edf5ff;font:16px system-ui;display:grid;place-items:center;padding:20px}"
    ".card{width:min(100%,600px);padding:28px;border:1px solid #26344c;border-radius:22px;background:linear-gradient(145deg,#131e32,#0b1220);box-shadow:0 20px 80px #0008}h1{color:#38bdf8;margin:0}p{color:#9aacc4}input,select,button{width:100%;padding:14px;margin-top:12px;border-radius:10px;border:1px solid #33445e;background:#080f1d;color:#fff;font:inherit}button{background:#38bdf8;color:#03111b;font-weight:700;cursor:pointer;border:0}a{color:#38bdf8}small{color:#9aacc4}</style><main class='card'><h1>AKU Video Download</h1><p>YouTube & supported media sites · LAN dashboard</p>"+body+"</main></html>")

class AKUWebHandler(BaseHTTPRequestHandler):
    server_version = "AKUVideo/1.0"
    def send_html(self, body, status=200):
        data = page(body).encode()
        self.send_response(status); self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.end_headers()
        try: self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_GET(self):
        if self.path != "/":
            self.send_html("<h2>Not found</h2><a href='/'>Home</a>",404); return
        self.send_html("<form method='post' action='/preview'><label>Media URL</label><input name='url' type='url' maxlength='4096' placeholder='https://…' required><button>Analyze link</button></form><small>Use only content you are authorized to download. Two concurrent jobs maximum.</small>")
    def do_POST(self):
        if self.path not in ("/preview","/download"):
            self.send_html("<h2>Not found</h2>",404); return
        try:
            length = int(self.headers.get("Content-Length","0"))
            if length <= 0 or length > 8192: raise ValueError("Invalid request size.")
            params = parse_qs(self.rfile.read(length).decode("utf-8","replace"), max_num_fields=10)
            url = params.get("url",[""])[0].strip()
            if len(url)>4096: raise ValueError("URL too long.")
            url = expand_url(url)
            if self.path == "/preview":
                info = analyze(url)
                title = html.escape(info.get("title") or "Untitled")
                best = fmt_bytes(estimate(info))
                hd = fmt_bytes(estimate(info,720))
                body = f"<h2>{title}</h2><p>{html.escape(info.get('extractor_key','Media'))} · {int(info.get('duration') or 0)} sec</p><p>Estimated best video: {best}<br>Estimated up to 720p: {hd}</p><form method='post' action='/download'><input type='hidden' name='url' value='{html.escape(url,quote=True)}'><select name='quality'><option value='best'>Best available</option><option value='720p'>Up to 720p</option><option value='audio'>Audio only (source format)</option></select><button>Download to this device</button></form><p><a href='/'>Analyze another link</a></p>"
                self.send_html(body)
            else:
                if not MAX_JOBS.acquire(blocking=False):
                    self.send_html("<h2>Server busy</h2><p>Two downloads are already running. Try again shortly.</p><a href='/'>Back</a>",429); return
                tmp = tempfile.mkdtemp(prefix="aku-job-")
                with JOBS_LOCK: JOBS.add(tmp)
                try:
                    quality = params.get("quality",["best"])[0]
                    fmt = {"720p":"best[height<=720]/bestvideo[height<=720]+bestaudio/best","audio":"bestaudio/best"}.get(quality,"bestvideo+bestaudio/best")
                    opts = {"quiet":True,"no_warnings":True,"noplaylist":True,"format":fmt,"outtmpl":os.path.join(tmp,"%(title).120B [%(id)s].%(ext)s"),"max_filesize":2*1024**3}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url,download=True)
                        filename = ydl.prepare_filename(info)
                    if not os.path.isfile(filename):
                        stem = os.path.splitext(filename)[0]
                        candidates = [os.path.join(tmp,n) for n in os.listdir(tmp) if n.startswith(os.path.basename(stem))]
                        if not candidates: raise RuntimeError("Downloaded file could not be located.")
                        filename = candidates[0]
                    size = os.path.getsize(filename)
                    name = os.path.basename(filename).replace("\r","").replace("\n","")
                    self.send_response(200); self.send_header("Content-Type","application/octet-stream")
                    self.send_header("Content-Disposition", "attachment; filename*=UTF-8''"+quote(name))
                    self.send_header("Content-Length",str(size)); self.end_headers()
                    with open(filename,"rb") as f:
                        while True:
                            chunk=f.read(64*1024)
                            if not chunk: break
                            self.wfile.write(chunk)
                finally:
                    shutil.rmtree(tmp,ignore_errors=True)
                    with JOBS_LOCK: JOBS.discard(tmp)
                    MAX_JOBS.release()
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e: self.send_html("<h2>Request failed</h2><p>"+html.escape(str(e)[:500])+"</p><a href='/'>Try again</a>",400)
    def log_message(self, fmt, *args): print(f"[LAN] {self.client_address[0]} {fmt % args}")

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0",PORT),AKUWebHandler)
    server.daemon_threads = True
    print(f"AKU Video Download server running on http://{local_ip()}:{PORT}")
    print("Same Wi-Fi/hotspot devices can open the URL above. Ctrl+C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

def run_cli():
    dest=os.path.join(os.path.expanduser("~"),"Downloads","yt-downloads")
    os.makedirs(dest,exist_ok=True)
    print("AKU Video Download - YT & Universal")
    print(f"Web dashboard: http://{local_ip()}:{PORT} (starts with CLI)")
    server=threading.Thread(target=run_server,daemon=True); server.start()
    while True:
        try: url=input("\nURL / 11-character YouTube ID (exit to quit): ").strip()
        except (EOFError,KeyboardInterrupt): break
        if url.lower() in ("exit","quit","q"): break
        if not url: continue
        if re.fullmatch(r"[A-Za-z0-9_-]{11}",url): url="https://www.youtube.com/watch?v="+url
        try:
            print("Analyzing…"); info=analyze(url)
            print(f"{info.get('title','Untitled')} · {int(info.get('duration') or 0)} sec · est. {fmt_bytes(estimate(info))}")
            q=input("[1] Best video [2] Up to 720p [3] Audio source (default 1): ").strip()
            fmt={"2":"best[height<=720]/bestvideo[height<=720]+bestaudio/best","3":"bestaudio/best"}.get(q,"bestvideo+bestaudio/best")
            opts={"format":fmt,"outtmpl":os.path.join(dest,"%(title).120B [%(id)s].%(ext)s"),"noplaylist":True}
            with yt_dlp.YoutubeDL(opts) as ydl: ydl.download([expand_url(url)])
            print("Download complete:",dest)
        except Exception as e: print("Error:",e)
    print("Goodbye.")

if __name__=="__main__":
    run_server() if "--server" in sys.argv else run_cli()
