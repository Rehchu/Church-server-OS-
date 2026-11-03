"""Small helpers shared by every module: run a command, read JSON, humanise bytes."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str], timeout: int = 60, input_text: str | None = None, check: bool = False) -> dict:
    """Run a command and always come back with something readable.

    Returns {"ok", "code", "out", "err", "cmd", "seconds"}. Never raises on a
    non-zero exit unless check=True, because the caller usually wants to show
    the error in the dashboard rather than crash the request.
    """
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)
        res = {"ok": p.returncode == 0, "code": p.returncode, "out": p.stdout, "err": p.stderr}
    except FileNotFoundError:
        res = {"ok": False, "code": 127, "out": "", "err": f"{cmd[0]}: not installed"}
    except subprocess.TimeoutExpired:
        res = {"ok": False, "code": 124, "out": "", "err": f"timed out after {timeout}s"}
    res["cmd"] = " ".join(cmd)
    res["seconds"] = round(time.time() - t0, 2)
    if check and not res["ok"]:
        raise RuntimeError(res["err"] or res["out"] or res["cmd"])
    return res


def run_stream(cmd: list[str], timeout: int = 1800, log=None) -> dict:
    """Stream long-running tool output, retaining a bounded tail and its exit status.

    Used for image pulls: the CLI/installer can tee this output into its log.
    Unlike run(), a timeout preserves the diagnostic output received so far.
    Never pass commands that print credentials to this helper.
    """
    log = log or (lambda line: print(line, flush=True))
    started = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, start_new_session=True)
    except FileNotFoundError:
        return {"ok": False, "code": 127, "out": "", "err": f"{cmd[0]}: not installed"}
    output = queue.Queue()

    def reader():
        try:
            for line in proc.stdout:
                output.put(line)
        finally:
            proc.stdout.close()
            output.put(None)

    threading.Thread(target=reader, daemon=True).start()
    tail, expired = "", False
    def kill():
        try:
            if os.name == "posix":
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass

    while True:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            expired = True
            kill()
            break
        try:
            line = output.get(timeout=min(remaining, 0.25))
        except queue.Empty:
            continue
        if line is None:
            break
        tail = (tail + line)[-262144:]
        log(line.rstrip("\r\n"))
    try:
        proc.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        expired = True
        kill()
        proc.wait()
    code = 124 if expired else proc.returncode
    err = f"timed out after {timeout}s" if expired else (tail if code else "")
    return {"ok": code == 0, "code": code, "out": tail, "err": err,
            "seconds": round(time.monotonic() - started, 2)}


def read_json(path: str | os.PathLike, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: str | os.PathLike, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def read_text(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return default


def human_bytes(n: float | int | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dir_size(path, limit_seconds: float = 2.0) -> int | None:
    """Total bytes under path, giving up (None) if it takes too long."""
    t0 = time.time()
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
            if time.time() - t0 > limit_seconds:
                return None
    except OSError:
        return None
    return total
