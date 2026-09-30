# StepThrough – step-by-step code visualizer

Static site. No build step, no backend. JavaScript and Python run in the visitor's browser
(Python via Pyodide, loaded from a CDN the first time it is used).

## Run locally
Open `index.html` in a browser (or `npx serve .`).

## Deploy to Vercel
1. Put `index.html` in a folder, push it to a GitHub repo.
2. vercel.com -> Add New -> Project -> import the repo.
3. Framework Preset: **Other**. Leave Build Command and Output Directory empty. Deploy.

CLI alternative: `npm i -g vercel`, then run `vercel --prod` inside the folder.

## How it works
- JavaScript: the code is parsed with acorn, trace calls are inserted before every statement, and every step is recorded.
- Python: `sys.settrace` records each line event, the call stack and local variables.
- The UI replays the recorded steps, so going back is instant.

## Not supported yet
C / C++ / Java need a real compiler and debugger, so they need a Docker backend
(Render, Railway or Fly.io, not Vercel functions). Python `input()` and imports of
non-bundled packages are not supported.
