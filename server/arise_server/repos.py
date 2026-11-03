"""The Arise repos on the server, kept in step with GitHub both ways.

Bradly (Oct 28): "download all the arise repos to the server and keep them
synced with GitHub and the server". Each repo in [github] repos gets a working
folder, /srv/arise/repos/<name>. Every 15 minutes arise-repos.service (user
arise-git) fetches, fast-forwards, and pushes commits made here.

What it never does: commit for anyone, merge or rebase, force-push, run a repo's
hooks, push a commit that carries a credential or a file GitHub would refuse
(over 100 MB), or push where the repo's policy says not to:
  all       pull and push any branch (the default)
  branches  pull everything; push branches other than the default one
  none      pull only
Defaults: AriseHub "none" (a push to main deploys the live site through
Cloudflare Workers Builds, and a branch push leaves a preview version that
blocks Cloudflare secret changes; AriseHub's CLAUDE.md), Arise-Youtube-Automation
"branches" (its main is edited on the PC; SERVER_HANDOFF.md). [repos] in
arise.toml changes them.

These folders are not the automator job's checkout (/srv/arise/automator) and
not the search archive's clones (/srv/arise/archive): each stays independent.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from .config import load
from .util import now_iso

ROOT = "/srv/arise/repos"
STATE = "/var/lib/arise/repos/status.json"
DEFAULT_POLICY = {"AriseHub": "none", "Arise-Youtube-Automation": "branches"}
BIG = 100 * 1024 * 1024            # GitHub refuses a file over 100 MB
# Real credential shapes only (a doc that names a prefix does not match).
SECRET_RE = re.compile(
    r"(1//0[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
    r"github_pat_[A-Za-z0-9_]{40,}|sk-ant-[A-Za-z0-9_-]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"re_[A-Za-z0-9]{20,}_[A-Za-z0-9]{10,})")
SECRET_PATHS = re.compile(r"(^|/)(token[^/]*\.json|[^/]*token[^/]*\.json|client_secret[^/]*\.json|deploy_key[^/]*|[^/]*\.pem|[^/]*\.key|\.env)$", re.I)


def config() -> dict:
    cfg = load()
    raw = cfg.raw.get("repos", {}) if isinstance(cfg.raw, dict) else {}
    pol = dict(DEFAULT_POLICY)
    pol.update({str(k): str(v) for k, v in (raw.get("policy") or {}).items()})
    return {"root": raw.get("root", ROOT), "repos": list(cfg.github.repos), "policy": pol,
            "enabled": bool(raw.get("enabled", True)), "token_file": cfg.github.token_file}


def name_of(full: str) -> str:
    return full.split("/", 1)[-1]


def policy_for(name: str, policy: dict) -> str:
    """Case-insensitive lookup (the repo list and GitHub disagree on case for some names)."""
    for k, v in policy.items():
        if k.lower() == name.lower():
            return v if v in ("all", "branches", "none") else "none"
    return "all"


def plan(ahead: int, behind: int, dirty: bool, branch: str, default_branch: str, policy: str, upstream: bool) -> dict:
    """Pure: what one sync does with one repo."""
    if not branch:
        return {"do": "stop", "why": "detached HEAD: check out a branch"}
    if not upstream:
        if not ahead:
            return {"do": "none", "why": f"{branch} has no upstream and nothing new"}
        if policy == "all" or (policy == "branches" and branch != default_branch):
            return {"do": "push-new", "why": f"new branch {branch} ({ahead} commit(s))"}
        return {"do": "hold", "why": f"new branch {branch} is not pushed from the server (policy: {policy})"}
    if ahead and behind:
        return {"do": "stop", "why": f"diverged: {ahead} commit(s) here and {behind} on GitHub; settle it by hand (no merge or rebase is done for you)"}
    if behind:
        return {"do": "pull", "why": f"{behind} new on GitHub" + (" (uncommitted edits here: pulled only if they do not overlap)" if dirty else "")}
    if ahead:
        if policy == "none":
            return {"do": "hold", "why": "pull-only repo: commits here are not pushed"}
        if policy == "branches" and branch == default_branch:
            return {"do": "hold", "why": f"{branch} is not pushed from the server (policy: branches)"}
        return {"do": "push", "why": f"{ahead} commit(s) to push"}
    return {"do": "none", "why": "up to date" + (", with uncommitted edits" if dirty else "")}


def scan_outgoing(blobs: list[tuple[str, int]], patch: str) -> list[str]:
    """Pure: refusals for an outgoing push, over EVERY commit in it (a secret added and removed again
    would still travel in the history). blobs = [(path, size)] of every object in the range; patch = the
    added lines of every commit, as `git log -p` prints them with a '### <path>' marker per file.
    Paths only in the result, never the matched text."""
    bad = []
    for path, size in blobs:
        if size > BIG:
            bad.append(f"{path}: {size // (1024 * 1024)} MB, over GitHub's 100 MB limit")
        elif SECRET_PATHS.search(path):
            bad.append(f"{path}: a credential-shaped file name")
    current = "?"
    for ln in patch.splitlines():
        if ln.startswith("+++ b/"):
            current = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++") and SECRET_RE.search(ln):
            msg = f"{current}: contains something shaped like a credential"
            if msg not in bad:
                bad.append(msg)
    return bad


def _token() -> str:
    cdir = os.environ.get("CREDENTIALS_DIRECTORY")
    for p in ([os.path.join(cdir, "github-token")] if cdir else []) + [config()["token_file"]]:
        try:
            t = open(p).read().strip()
            if t:
                return t
        except OSError:
            pass
    return ""


def _g(repo: str | None, args: list[str], token: str, timeout: int = 600) -> dict:
    from .backups import _git
    base = ["-c", "core.hooksPath=/dev/null"] + (["-C", repo] if repo else [])
    r = _git(base + args, token, timeout=timeout)
    if token:
        for k in ("out", "err"):
            r[k] = (r.get(k) or "").replace(token, "***")
    return r


def _state_read() -> dict:
    try:
        return json.loads(Path(STATE).read_text())
    except (OSError, ValueError):
        return {}


def _state_write(d: dict):
    try:
        Path(STATE).parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE + ".tmp"
        Path(tmp).write_text(json.dumps(d, indent=1))
        os.replace(tmp, STATE)
    except OSError:
        pass


def _one(full: str, c: dict, token: str, dry_run: bool) -> dict:
    name = name_of(full)
    path = os.path.join(c["root"], name)
    pol = policy_for(name, c["policy"])
    row = {"repo": full, "name": name, "path": path, "policy": pol, "when": now_iso()}
    if not os.path.isdir(os.path.join(path, ".git")):
        if dry_run:
            return {**row, "do": "clone", "ok": True, "why": "not here yet"}
        r = _g(None, ["clone", "--quiet", f"https://github.com/{full}.git", path], token, timeout=3600)
        if r["ok"]:
            _g(path, ["config", "core.sharedRepository", "group"], token)
        return {**row, "do": "clone", "ok": r["ok"], "why": "cloned" if r["ok"] else (r["err"] or r["out"]).strip()[-300:]}
    f = _g(path, ["fetch", "--quiet", "--prune", "origin"], token)
    if not f["ok"]:
        return {**row, "do": "stop", "ok": False, "why": "fetch failed: " + (f["err"] or f["out"]).strip()[-300:]}
    branch = _g(path, ["symbolic-ref", "--quiet", "--short", "HEAD"], token)["out"].strip()
    default = _g(path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], token)["out"].strip().replace("origin/", "") or "main"
    up = _g(path, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], token)
    upstream = up["ok"]
    ahead = behind = 0
    if upstream:
        lr = _g(path, ["rev-list", "--left-right", "--count", "HEAD...@{u}"], token)["out"].split()
        if len(lr) == 2:
            ahead, behind = int(lr[0]), int(lr[1])
    elif branch:
        n = _g(path, ["rev-list", "--count", "HEAD", "--not", "--remotes=origin"], token)["out"].strip()
        ahead = int(n) if n.isdigit() else 0
    dirty = bool(_g(path, ["status", "--porcelain"], token)["out"].strip())
    p = plan(ahead, behind, dirty, branch, default, pol, upstream)
    row.update({"branch": branch, "default": default, "ahead": ahead, "behind": behind, "dirty": dirty, **p})
    if dry_run or p["do"] in ("none", "hold"):
        return {**row, "ok": p["do"] != "stop"}
    if p["do"] == "stop":
        return {**row, "ok": False}
    if p["do"] == "pull":
        r = _g(path, ["merge", "--ff-only", "--quiet", "@{u}"], token)
        return {**row, "ok": r["ok"], "why": ("pulled " + str(behind)) if r["ok"] else "pull blocked: " + (r["err"] or r["out"]).strip()[-300:]}
    # push / push-new: check everything that would leave, commit by commit
    rng = ["@{u}..HEAD"] if p["do"] == "push" else ["HEAD", "--not", "--remotes=origin"]
    objs = _g(path, ["rev-list", "--objects", *rng], token)["out"].splitlines()
    blobs = []
    if objs:
        import subprocess
        q = "\n".join(o.split(" ", 1)[0] for o in objs) + "\n"
        names = {o.split(" ", 1)[0]: (o.split(" ", 1)[1] if " " in o else "") for o in objs}
        cp = subprocess.run(["git", "-C", path, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                            input=q, capture_output=True, text=True, timeout=300)
        for ln in cp.stdout.splitlines():
            parts = ln.split()
            if len(parts) == 3 and parts[1] == "blob":
                blobs.append((names.get(parts[0], parts[0]), int(parts[2])))
    patch = _g(path, ["log", "-p", "--no-color", "--format=", *rng], token, timeout=900)["out"]
    refused = scan_outgoing(blobs, patch)
    if refused:
        return {**row, "ok": False, "do": "refused", "why": "not pushed: " + "; ".join(refused[:5])}
    args = ["push", "--quiet", "origin", branch] if p["do"] == "push" else ["push", "--quiet", "--set-upstream", "origin", branch]
    r = _g(path, args, token)
    return {**row, "ok": r["ok"], "why": (f"pushed {ahead or 'the new branch'}" if r["ok"] else "push failed: " + (r["err"] or r["out"]).strip()[-300:])}


def sync(only: str | None = None, dry_run: bool = False) -> dict:
    c = config()
    if load().demo:
        return status()
    token = _token()
    rows = []
    for full in c["repos"]:
        if only and name_of(full).lower() != only.lower():
            continue
        try:
            rows.append(_one(full, c, token, dry_run))
        except Exception as e:  # noqa: BLE001 - one bad repo must not stop the rest
            rows.append({"repo": full, "name": name_of(full), "ok": False, "do": "stop", "why": f"error: {e}"})
    if not dry_run:
        st = _state_read()
        st.update({r["name"]: r for r in rows})
        st["_last"] = now_iso()
        st["_token"] = bool(token)
        _state_write(st)
        bad = [r for r in rows if not r.get("ok")]
        if bad:
            try:
                from . import push
                push.send("Repos need you", "; ".join(f"{r['name']}: {r.get('why', '')}" for r in bad)[:300], url="/#settings",
                          tag="repos", throttle_s=6 * 3600)
            except Exception:  # noqa: BLE001
                pass
    return {"ok": all(r.get("ok") for r in rows), "repos": rows, "dry_run": dry_run, "token": bool(token)}


def status() -> dict:
    c = config()
    if load().demo:
        rows = []
        for full in c["repos"]:
            n = name_of(full)
            pol = policy_for(n, c["policy"])
            rows.append({"repo": full, "name": n, "path": os.path.join(c["root"], n), "policy": pol, "branch": "main", "ahead": 0, "behind": 0,
                         "dirty": False, "do": "none", "ok": True, "why": "up to date", "when": now_iso(), "sample": True})
        return {"demo": True, "repos": rows, "last": now_iso(), "token": True, "root": c["root"]}
    st = _state_read()
    rows = [st.get(name_of(f), {"repo": f, "name": name_of(f), "do": "clone", "ok": False, "why": "not synced yet",
                                "policy": policy_for(name_of(f), c["policy"])}) for f in c["repos"]]
    return {"demo": False, "repos": rows, "last": st.get("_last"), "token": st.get("_token", False), "root": c["root"]}
