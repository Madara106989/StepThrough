"""StepThrough backend. POST /trace {"language":"cpp","code":"..."} -> {"steps":[...],"error":null|str}
Standard library only. Needs g++ and gdb installed (see Dockerfile)."""
import json, os, resource, shutil, signal, subprocess, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8080"))
ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")  # set to your Vercel URL in production
SLOTS = threading.Semaphore(2)  # at most 2 traces at once
HITS = {}
UNBUF = '#include <cstdio>\n__attribute__((constructor)) static void st_unbuf(){ setvbuf(stdout, nullptr, _IONBF, 0); }\n'


def limits(cpu, mem):
    def apply():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (20 * 2**20, 20 * 2**20))
    return apply


def run(cmd, cwd, env, timeout, cpu, mem):
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, errors="replace",
                         start_new_session=True, preexec_fn=limits(cpu, mem))
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, "timeout"


def trace_cpp(code):
    d = tempfile.mkdtemp(prefix="st_")
    try:
        with open(os.path.join(d, "main.cpp"), "w") as f:
            f.write(code)
        with open(os.path.join(d, "unbuf.cpp"), "w") as f:
            f.write(UNBUF)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": d, "LANG": "C.UTF-8"}
        rc, out = run(["g++", "-std=c++17", "-g", "-O0", "-fno-inline", "-o", "prog", "main.cpp", "unbuf.cpp"],
                      d, env, 30, 25, 2 * 2**30)
        if rc != 0:
            msg = "Compile timed out." if rc is None else out.strip()[:3000]
            return {"steps": [], "error": "Compile error:\n" + msg}
        env.update(TRACE_SRC="main.cpp", TRACE_OUT=os.path.join(d, "result.json"),
                   PROG_OUT=os.path.join(d, "out.txt"), MAX_STEPS="1500", MAX_DEPTH="150")
        open(os.path.join(d, "out.txt"), "w").close()
        rc, out = run(["gdb", "-q", "-batch", "-nx", "-x", os.path.join(HERE, "gdb_trace.py"),
                       "--args", os.path.join(d, "prog")], d, env, 40, 40, 3 * 2**30)
        if rc is None:
            return {"steps": [], "error": "Timed out. Is there an infinite loop or a very long run?"}
        try:
            with open(env["TRACE_OUT"]) as f:
                return json.load(f)
        except Exception:
            return {"steps": [], "error": "Tracing failed:\n" + out.strip()[-800:]}
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._send(200, {"ok": True}) if self.path == "/health" else self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/trace":
            return self._send(404, {"error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        now = time.time()
        HITS[ip] = [t for t in HITS.get(ip, []) if now - t < 60] + [now]
        if len(HITS[ip]) > 12:
            return self._send(429, {"steps": [], "error": "Too many runs. Wait a minute and try again."})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 60000:
                return self._send(413, {"steps": [], "error": "Code is too long (limit 60 KB)."})
            req = json.loads(self.rfile.read(n))
            code, lang = req["code"], req.get("language", "cpp")
        except Exception:
            return self._send(400, {"steps": [], "error": "Bad request."})
        if lang != "cpp":
            return self._send(400, {"steps": [], "error": "Unsupported language: %s" % lang})
        if not SLOTS.acquire(timeout=30):
            return self._send(503, {"steps": [], "error": "Server is busy. Try again in a moment."})
        try:
            self._send(200, trace_cpp(code))
        except OSError as e:
            self._send(500, {"steps": [], "error": "Server is missing a tool (g++ or gdb): %s" % e})
        except Exception as e:
            self._send(500, {"steps": [], "error": "Internal error: %s" % e})
        finally:
            SLOTS.release()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("StepThrough backend on port", PORT, flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
