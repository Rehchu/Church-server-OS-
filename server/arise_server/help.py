"""The Help app: the repository's docs rendered inside the dashboard. Members
see the portal guide; admins see everything (round 3, 35).

Rendering: python-markdown when it is installed, a small built-in renderer
otherwise. Every "<" in a document is escaped before rendering, so a doc can
never put a script or a tag into the page: only Markdown syntax makes HTML.
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from .config import load

MEMBER_DOCS = ("PORTAL-GUIDE",)
HIDDEN = {"QUESTIONS", "PRE-WIPE"}   # the multiple-choice sheet and the wipe checklist: not help


def _root() -> Path:
    return load().repo_root


def _files() -> list[Path]:
    root = _root()
    out = [root / "README.md"] if (root / "README.md").is_file() else []
    docs = root / "docs"
    if docs.is_dir():
        out += sorted(p for p in docs.glob("*.md") if p.stem not in HIDDEN)
    return out


def _name(p: Path) -> str:
    return "README" if p.name == "README.md" else p.stem


def title_of(text: str, fallback: str) -> str:
    """The first heading, or the file name. Pure."""
    for line in text.splitlines():
        m = re.match(r"^#\s+(.*)", line)
        if m:
            return m.group(1).strip()
    return fallback


def _allowed(name: str, role: str) -> bool:
    return role == "admin" or name in MEMBER_DOCS


def docs(role: str = "admin") -> dict:
    out = []
    for p in _files():
        n = _name(p)
        if not _allowed(n, role):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append({"name": n, "title": title_of(text, n), "size": len(text), "lines": text.count("\n") + 1,
                    "blurb": _blurb(text)})
    if role != "admin":
        out = [d for d in out if d["name"] in MEMBER_DOCS] or [{"name": "PORTAL-GUIDE", "title": "The portal guide", "size": 0, "lines": 0, "blurb": "Not written on this box yet."}]
    return {"docs": out, "role": role, "demo": load().demo}


def _blurb(text: str) -> str:
    for line in text.splitlines()[1:]:
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("|") and not s.startswith("```") and not s.startswith("-"):
            return re.sub(r"[*`_\[\]]", "", s)[:140]
    return ""


def render_markdown(src: str) -> str:
    """Markdown to HTML with raw HTML neutralised. Pure."""
    safe = src.replace("<", "&lt;")
    try:
        import markdown  # type: ignore
        return markdown.markdown(safe, extensions=["tables", "fenced_code", "toc"], output_format="html")
    except ImportError:
        return _tiny(safe)


def _tiny(src: str) -> str:
    out, in_code, in_list, in_table = [], False, False, False
    inline = lambda s: re.sub(r"`([^`]+)`", r"<code>\1</code>", re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)))
    for line in src.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            out.append("<pre><code>" if in_code else "</code></pre>")
            continue
        if in_code:
            out.append(html.escape(line, quote=False).replace("&amp;lt;", "&lt;"))
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
            continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(re.sub(r'^\s*[-*]\s+', '', line))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip():
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def doc(name: str, role: str = "admin") -> dict:
    if not re.match(r"^[A-Za-z0-9_-]+$", name or "") or not _allowed(name, role):
        return {"ok": False, "err": "no such document"}
    p = _root() / ("README.md" if name == "README" else f"docs/{name}.md")
    if not p.is_file() or name in HIDDEN:
        return {"ok": False, "err": "no such document"}
    text = p.read_text(encoding="utf-8")
    return {"ok": True, "name": name, "title": title_of(text, name), "html": render_markdown(text), "demo": load().demo}


def search(q: str, role: str = "admin", limit: int = 30) -> dict:
    q = (q or "").strip().lower()
    hits = []
    if len(q) < 2:
        return {"q": q, "hits": hits}
    for p in _files():
        n = _name(p)
        if not _allowed(n, role):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        title = title_of(text, n)
        for i, line in enumerate(text.splitlines()):
            if q in line.lower():
                s = re.sub(r"[*`_|#]", "", line).strip()
                hits.append({"name": n, "title": title, "line": i + 1, "snippet": s[:160]})
                if len([h for h in hits if h["name"] == n]) >= 4:
                    break
        if len(hits) >= limit:
            break
    return {"q": q, "hits": hits[:limit]}
