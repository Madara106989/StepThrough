# Runs INSIDE gdb:  gdb -q -batch -nx -x gdb_trace.py --args ./prog
# Steps through the user's program line by line and writes every step to a JSON file.
import os, re, json

try:
    import gdb
except ImportError:  # lets the pure helpers be unit-tested outside gdb
    gdb = None

SRC = os.environ.get("TRACE_SRC", "main.cpp")
RES = os.environ.get("TRACE_OUT", "result.json")
POUT = os.environ.get("PROG_OUT", "out.txt")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "1500"))
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "150"))


def fmt(s):
    s = " ".join(str(s).split())
    return s if len(s) <= 50 else s[:47] + "..."


def split_top(s):
    """Split 'a, b, {c, d}' on top-level commas only."""
    parts, depth, cur, quote = [], 0, "", False
    for ch in s:
        if ch == '"':
            quote = not quote
        if not quote:
            if ch in "{(<[":
                depth += 1
            elif ch in "})>]":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(cur.strip())
                cur = ""
                continue
        cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_container(s):
    """Turn libstdc++ pretty-printer text (std::vector of length 3 ... = {1, 2, 3}) into cells."""
    if not re.match(r"^std::(vector|array|deque|list|set|multiset|forward_list)\b", s):
        return None
    if re.search(r"of length 0\b", s) and "= {" not in s:
        return {"arr": [], "more": False}
    m = re.search(r"=\s*\{(.*)\}$", s, re.S)
    if not m:
        return None
    inner = re.sub(r"std::[\w:]+(<[^{}]*>)? of length \d+, capacity \d+ = ", "", m.group(1))
    inner = re.sub(r"std::[\w:]+(<[^{}]*>)? of length 0, capacity \d+", "{}", inner)
    items = split_top(inner)
    return {"arr": [fmt(x) for x in items[:30]], "more": len(items) > 30}


def ser(v):
    try:
        t = v.type.strip_typedefs()
        if t.code == gdb.TYPE_CODE_ARRAY:
            elem = t.target().strip_typedefs()
            if elem.code in (gdb.TYPE_CODE_INT, gdb.TYPE_CODE_CHAR) and elem.sizeof == 1:
                return fmt(v)  # C string
            lo, hi = t.range()
            return {"arr": [fmt(v[i]) for i in range(lo, min(hi, lo + 29) + 1)], "more": hi - lo + 1 > 30}
        s = str(v)
        return parse_container(s) or fmt(s)
    except Exception as e:
        return "?"


def is_user(fr):
    try:
        st = fr.find_sal().symtab
        return st is not None and os.path.basename(st.filename) == os.path.basename(SRC)
    except Exception:
        return False


def frame_vars(fr, line):
    rows, seen = [], set()
    try:
        b = fr.block()
    except Exception:
        return []
    while b is not None:
        for sym in b:
            if not (sym.is_variable or sym.is_argument) or sym.name in seen:
                continue
            if sym.is_variable and sym.line and sym.line > line:
                continue  # declared further down, not alive yet
            try:
                rows.append((0 if sym.is_argument else 1, sym.line or 0, sym.name, ser(sym.value(fr))))
                seen.add(sym.name)
            except Exception:
                pass
        if b.function is not None:
            break
        b = b.superblock
    rows.sort(key=lambda r: (r[0], r[1]))
    return [[r[2], r[3]] for r in rows]


def read_out():
    try:
        with open(POUT, errors="replace") as f:
            return f.read()[-5000:]
    except Exception:
        return ""


def main():
    gdb.execute("set pagination off")
    gdb.execute("set confirm off")
    gdb.execute("set print elements 30")
    gdb.execute("set print pretty off")
    gdb.execute("set style enabled off")
    steps, err, crashed = [], None, [None]

    def on_stop(ev):
        if isinstance(ev, gdb.SignalEvent):
            crashed[0] = ev.stop_signal

    gdb.events.stop.connect(on_stop)
    try:
        gdb.execute("break main", to_string=True)
        gdb.execute("run > %s < /dev/null" % POUT, to_string=True)
    except gdb.error as e:
        err = "Could not start the program: %s" % e
    guard = 0
    while err is None and len(steps) < MAX_STEPS and guard < MAX_STEPS * 4:
        guard += 1
        try:
            if gdb.selected_inferior().pid == 0:
                break
            fr = gdb.newest_frame()
        except gdb.error:
            break
        if not is_user(fr):
            try:
                gdb.execute("finish", to_string=True)
            except gdb.error:
                try:
                    gdb.execute("step", to_string=True)
                except gdb.error:
                    break
            continue
        chain, f = [], fr
        while f is not None and len(chain) <= MAX_DEPTH + 1:
            if is_user(f):
                chain.append(f)
            f = f.older()
        if len(chain) > MAX_DEPTH:
            err = "Recursion too deep (over %d calls). Missing base case?" % MAX_DEPTH
            break
        chain.reverse()
        stack = []
        for f in chain:
            ln = f.find_sal().line
            stack.append({"name": f.name() or "?", "vars": frame_vars(f, ln)})
        steps.append({"line": fr.find_sal().line, "stack": stack, "txt": read_out()})
        if crashed[0]:
            err = "Program crashed with signal %s on line %d." % (crashed[0], fr.find_sal().line)
            break
        try:
            gdb.execute("step", to_string=True)
        except gdb.error:
            break
    if err is None and crashed[0]:
        err = "Program crashed with signal %s." % crashed[0]
    if err is None and len(steps) >= MAX_STEPS:
        err = "Stopped after %d steps (possible infinite loop)." % MAX_STEPS
    if steps:
        steps.append(dict(steps[-1], txt=read_out()))  # final step shows the complete output
    try:
        gdb.execute("kill", to_string=True)
    except Exception:
        pass
    with open(RES, "w") as f:
        json.dump({"steps": steps, "error": err}, f)


if gdb is not None:
    main()
