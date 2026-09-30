# StepThrough - step-by-step code visualizer

| Language   | Where it runs                                  | Needs a server? |
|------------|------------------------------------------------|-----------------|
| JavaScript | In the visitor's browser (acorn instrumentation) | No              |
| Python     | In the visitor's browser (Pyodide + sys.settrace) | No              |
| C++        | On your backend (g++ + gdb, in Docker)          | Yes             |

```
index.html   -> the website (deploy on Vercel)
backend/     -> C++ tracing API (deploy on Render / Railway / Fly.io, NOT Vercel)
```

## 1. Deploy the website on Vercel
1. Push this folder to GitHub.
2. vercel.com -> Add New -> Project -> import the repo.
3. Framework Preset: **Other**. Root Directory: the folder that contains `index.html`. No build command. Deploy.

JavaScript and Python work right away.

## 2. Deploy the C++ backend (Render example)
1. On render.com choose New -> Web Service, connect the repo, set Root Directory to `backend`, Runtime: **Docker**.
2. Deploy. You get a URL like `https://stepthrough-api.onrender.com`. Check `<url>/health` returns `{"ok": true}`.
3. Set the environment variable `ALLOWED_ORIGIN` to your Vercel URL.
4. Open `index.html`, set `const CPP_API="https://stepthrough-api.onrender.com";`, commit and push. Vercel redeploys.

Free Render services sleep when idle, so the first C++ run after a while can take about a minute.

## Run everything locally
```
cd backend && docker build -t stepthrough-api . && docker run --rm -p 8080:8080 stepthrough-api
# then open index.html; on localhost it uses http://localhost:8080 automatically
```

## Security notes for the C++ backend
It compiles and runs strangers' code. The Dockerfile uses a non-root user, and the server limits CPU time, memory,
output size, request size, concurrency (2) and requests per IP (12/min). Also run it with no secrets in the
environment and, ideally, with the container's network disabled or restricted, and consider gVisor or nsjail
before opening it to the public.

## Known limits
- Python `input()` and C++ `cin` get no input (stdin is empty).
- Runs stop after 1500 steps or 150 nested calls.
- C++ locals on the line where they are declared may briefly show a garbage value before that line runs.
- Java is not supported yet (the same backend approach works with jdb).
