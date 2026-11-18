#!/usr/bin/env python3
"""Audit the static site's local references without network access or dependencies.

The default scope is the public site (root, blog, eco, emprender, mis_sitios,
viajes). --include-archives also inspects the teaching examples and demos.
The parser ignores HTML comments, script bodies and external URLs. It does not
execute JavaScript, validate third-party services, or implement HTML conformance
checking. CSS files linked by the inspected pages are followed recursively.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import unquote, urljoin, urlsplit


ORIGIN = "https://audit.invalid"
MAIN_DIRS = {"blog", "eco", "emprender", "mis_sitios", "viajes"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
SKIP_SCHEMES = {"data", "javascript", "mailto", "tel", "sms", "blob"}


def issue_key(issue: dict) -> tuple[str, str, str]:
    """A baseline survives edits that only move an existing issue to a new line."""
    return (issue["code"], issue["file"], issue.get("url", issue.get("detail", "")))


def resolve_local(source: str, url: str, base_url: str | None = None):
    """Return a root-relative path and fragment, or None for external URLs.

    Use URL semantics: ../ at the origin cannot escape the site root, Windows
    separators in HTML URLs are normalized, and query strings are not filenames.
    """
    cleaned = url.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("#") and len(cleaned) == 1:
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() in SKIP_SCHEMES:
        return None
    if parsed.scheme or parsed.netloc:
        if parsed.hostname != "audit.invalid" or parsed.scheme not in {"http", "https", ""}:
            return None
    absolute = urlsplit(urljoin(base_url or f"{ORIGIN}/{source}", cleaned))
    if absolute.hostname != "audit.invalid":
        return None
    decoded = unquote(absolute.path).replace("\\", "/")
    path = posixpath.normpath("/" + decoded.lstrip("/" )).lstrip("/")
    if decoded.endswith("/"):
        path = (path + "/" if path else "") + "index.html"
    if not path or path == ".":
        path = "index.html"
    return path, unquote(absolute.fragment)


def srcset_urls(value: str):
    """Tokenize candidates while preserving commas inside data URLs."""
    position = 0
    while position < len(value):
        while position < len(value) and (value[position].isspace() or value[position] == ","):
            position += 1
        start = position
        while position < len(value) and not value[position].isspace():
            position += 1
        candidate = value[start:position]
        if not candidate:
            break
        if candidate.endswith(","):
            yield candidate.rstrip(",")
            continue
        yield candidate
        parentheses = 0
        while position < len(value):
            char = value[position]
            position += 1
            if char == "(":
                parentheses += 1
            elif char == ")":
                parentheses = max(0, parentheses - 1)
            elif char == "," and not parentheses:
                break


def _css_unescape(value: str) -> str:
    def replacement(match):
        token = match.group(1)
        if re.fullmatch(r"[0-9a-fA-F]{1,6}\s?", token):
            number = int(token.strip(), 16)
            return chr(number) if 0 < number <= 0x10ffff else "\ufffd"
        return "" if token in {"\n", "\r\n", "\r"} else token
    return re.sub(r"\\([0-9a-fA-F]{1,6}\s?|\r\n|[\s\S])", replacement, value)


def _quoted_css(text: str, position: int):
    quote = text[position]
    start = position + 1
    position += 1
    while position < len(text):
        if text[position] == "\\":
            position += 2
        elif text[position] == quote:
            return text[start:position], position + 1
        else:
            position += 1
    return text[start:], len(text)


def css_urls(text: str):
    """Yield (url, line, is_import), excluding comments and ordinary strings."""
    position = 0
    while position < len(text):
        if text.startswith("/*", position):
            end = text.find("*/", position + 2)
            position = len(text) if end == -1 else end + 2
            continue
        if text[position] in "\"'":
            _, position = _quoted_css(text, position)
            continue
        start = position
        imported = re.match(r"@import\s+", text[position:], re.I)
        if imported:
            position += imported.end()
            if position < len(text) and text[position] in "\"'":
                value, position = _quoted_css(text, position)
                yield _css_unescape(value), text.count("\n", 0, start) + 1, True
                continue
        match = re.match(r"url\s*\(\s*", text[position:], re.I)
        boundary = position == 0 or not (text[position - 1].isalnum() or text[position - 1] in "_-")
        if match and boundary:
            position += match.end()
            if position < len(text) and text[position] in "\"'":
                value, position = _quoted_css(text, position)
                close = text.find(")", position)
                position = len(text) if close == -1 else close + 1
            else:
                begin = position
                while position < len(text):
                    if text[position] == "\\":
                        position += 2
                    elif text[position] == ")":
                        break
                    else:
                        position += 1
                value = text[begin:position].strip()
                position += position < len(text)
            yield _css_unescape(value), text.count("\n", 0, start) + 1, bool(imported)
            continue
        if position == start:
            position += 1


@dataclass
class Reference:
    url: str
    line: int
    kind: str
    disabled: bool = False


class Page(HTMLParser):
    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.source = source
        self.ids = defaultdict(list)
        self.anchors = set()
        self.references = []
        self.scripts = defaultdict(list)
        self.lang = ""
        self.base_url = f"{ORIGIN}/{source}"
        self._base_seen = False
        self._stack = []
        self._style_depth = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        line = self.getpos()[0]
        classes = (attributes.get("class") or "").split()
        disabled = ("disabled" in classes or "disabled" in attributes
                    or attributes.get("aria-disabled") == "true"
                    or any(state for _, state in self._stack))
        if tag not in VOID_TAGS:
            self._stack.append((tag, disabled))
        if tag == "html":
            self.lang = (attributes.get("lang") or "").lower()
        if attributes.get("id"):
            self.ids[attributes["id"]].append(line)
            self.anchors.add(attributes["id"])
        if tag == "a" and attributes.get("name"):
            self.anchors.add(attributes["name"])
        if tag == "base" and attributes.get("href") and not self._base_seen:
            self.base_url = urljoin(self.base_url, attributes["href"])
            self._base_seen = True
        for attribute in ("href", "xlink:href", "src", "poster"):
            value = attributes.get(attribute)
            if value is None or tag == "base":
                continue
            kind = "stylesheet" if tag == "link" and "stylesheet" in (attributes.get("rel") or "").split() else tag
            self.references.append(Reference(value, line, kind, disabled))
            if tag == "script" and attribute == "src":
                name = urlsplit(value).path.rsplit("/", 1)[-1].lower()
                if re.fullmatch(r"jquery(?:-[\d.]+)?(?:\.slim)?(?:\.min)?\.js", name):
                    self.scripts["jquery"].append((value, line))
                if name in {"bootstrap.js", "bootstrap.min.js", "bootstrap.bundle.js", "bootstrap.bundle.min.js"}:
                    self.scripts["bootstrap"].append((value, line))
        for candidate in srcset_urls(attributes.get("srcset") or ""):
            self.references.append(Reference(candidate, line, tag, disabled))
        for value, offset, is_import in css_urls(attributes.get("style") or ""):
            self.references.append(Reference(value, line + offset - 1, "stylesheet" if is_import else "css", disabled))
        if tag == "style":
            self._style_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "style":
            self._style_depth = max(0, self._style_depth - 1)
        for position in range(len(self._stack) - 1, -1, -1):
            if self._stack[position][0] == tag:
                del self._stack[position:]
                break

    def handle_data(self, data):
        if self._style_depth:
            for value, offset, is_import in css_urls(data):
                self.references.append(Reference(value, self.getpos()[0] + offset - 1,
                                                 "stylesheet" if is_import else "css"))


def site_html_files(root: Path, include_archives: bool = False):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or not path.is_file() or path.suffix.lower() != ".html":
            continue
        if include_archives or len(relative.parts) == 1 or relative.parts[0] in MAIN_DIRS:
            yield path


def audit(root: Path, include_archives: bool = False) -> dict:
    root = root.resolve()
    issues = {}
    pages = {}
    css_pending = set()
    css_done = set()
    references_checked = 0

    def add(code, source, line, detail, url=None, category="error", **extra):
        item = {"code": code, "file": source, "line": line, "detail": detail,
                "category": category, "count": 1, **extra}
        if url is not None:
            item["url"] = url
        key = issue_key(item)
        if key not in issues:
            item["lines"] = [line]
            issues[key] = item
        else:
            current = issues[key]
            current["count"] += item["count"]
            current["lines"] = sorted(set(current["lines"] + [line]))
            current["line"] = min(current["lines"])
            rank = {"disabled": 0, "warning": 1, "error": 2}
            if rank[category] > rank[current["category"]]:
                current["category"] = category

    def page(source):
        if source not in pages:
            parser = Page(source)
            parser.feed((root / source).read_text(encoding="utf-8-sig", errors="replace"))
            parser.close()
            pages[source] = parser
        return pages[source]

    def check_reference(source, reference, base_url=None):
        nonlocal references_checked
        try:
            resolved = resolve_local(source, reference.url, base_url)
        except ValueError:
            add("invalid_url", source, reference.line, "Malformed URL", url=reference.url,
                category="disabled" if reference.disabled else "error")
            return
        if resolved is None:
            return
        references_checked += 1
        target, fragment = resolved
        path = root / target
        if path.is_dir():
            target = target.rstrip("/") + "/index.html"
            path = root / target
        category = "disabled" if reference.disabled else "error"
        if not path.is_file():
            add("missing_file", source, reference.line, target,
                url=reference.url, category=category, kind=reference.kind)
            return
        if reference.kind == "stylesheet" and path.suffix.lower() == ".css":
            css_pending.add(target)
        if fragment and path.suffix.lower() == ".html" and fragment not in page(target).anchors:
            add("missing_fragment", source, reference.line, f"{target}#{fragment}",
                url=reference.url, category=category)
        if (reference.kind == "script" and reference.url.split("?", 1)[0].endswith("js/app.js")
                and target != "js/app.js"):
            add("shared_script_path", source, reference.line, "Shared app.js must resolve to js/app.js",
                url=reference.url, category=category)

    html_files = list(site_html_files(root, include_archives))
    for path in html_files:
        source = path.relative_to(root).as_posix()
        parsed = page(source)
        for identifier, lines in sorted(parsed.ids.items()):
            if len(lines) > 1:
                add("duplicate_id", source, lines[0], identifier, category="warning", count=len(lines))
        suffix = re.search(r"_(es|en)\.html$", source, re.I)
        if suffix and parsed.lang.split("-", 1)[0] != suffix.group(1).lower():
            add("language_mismatch", source, 1,
                f"lang={parsed.lang or '(missing)'}; filename={suffix.group(1).lower()}", category="warning")
        for library, scripts in sorted(parsed.scripts.items()):
            if len(scripts) > 1:
                add("duplicate_script", source, scripts[0][1], library, category="warning",
                    count=len(scripts), sources=sorted(url for url, _ in scripts))
        for reference in parsed.references:
            check_reference(source, reference, parsed.base_url)
    while css_pending - css_done:
        source = min(css_pending - css_done)
        css_done.add(source)
        text = (root / source).read_text(encoding="utf-8-sig", errors="replace")
        for value, line, imported in css_urls(text):
            check_reference(source, Reference(value, line, "stylesheet" if imported else "css"))

    ordered = [issues[key] for key in sorted(issues)]
    counts = Counter(item["category"] for item in ordered)
    return {"version": 1, "scope": "all" if include_archives else "main",
            "summary": {"html_files": len(html_files), "css_files": len(css_done),
                        "local_references": references_checked, "issues": len(ordered),
                        "errors": counts["error"], "warnings": counts["warning"],
                        "disabled_references": counts["disabled"]}, "issues": ordered}


def new_issues(report: dict, baseline: dict | None = None) -> list[dict]:
    known = {issue_key(item): item for item in (baseline or {}).get("issues", [])
             if item.get("category") != "disabled"}
    def occurrences(item):
        return item.get("count", len(item.get("lines", [])) or 1)
    return [item for item in report["issues"]
            if item["category"] != "disabled"
            and (issue_key(item) not in known
                 or occurrences(item) > occurrences(known[issue_key(item)]))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--include-archives", action="store_true")
    parser.add_argument("--json", type=Path, metavar="PATH", help="Write the complete deterministic report")
    parser.add_argument("--baseline", type=Path, help="Fail on new issues or growing occurrence counts compared with this JSON report")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        parser.error("--root must point to an existing site directory")
    report = audit(args.root, args.include_archives)
    baseline = None
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        if baseline.get("scope") != report["scope"]:
            parser.error("The baseline scope must match --include-archives")
    fresh = new_issues(report, baseline)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"HTML: {summary['html_files']}; CSS: {summary['css_files']}; "
          f"local references: {summary['local_references']}")
    print(f"Errors: {summary['errors']}; warnings: {summary['warnings']}; "
          f"disabled/planned references: {summary['disabled_references']}")
    print(f"{'New or worsened issues' if baseline is not None else 'Issues requiring review'}: {len(fresh)}")
    for item in fresh[:20]:
        print(f"  {item['file']}:{item['line']}: {item['code']}: {item.get('url', item['detail'])}")
    if len(fresh) > 20:
        print(f"  ... {len(fresh) - 20} more; use --json for the complete report.")
    return 1 if fresh else 0


if __name__ == "__main__":
    raise SystemExit(main())
