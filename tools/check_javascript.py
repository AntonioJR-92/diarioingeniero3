#!/usr/bin/env python3
"""Check active JavaScript syntax without executing application code or fetching URLs.

Requires Python 3.9+ and Node.js 18+. By default, checks the main website.
Use --include-archives to also inspect the archived teaching exercises and demos.
"""

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlsplit


MAIN_DIRECTORIES = {"blog", "eco", "emprender", "mis_sitios", "viajes"}
SCRIPT_TYPES = {
    "", "text/javascript", "application/javascript", "application/x-javascript",
    "text/ecmascript", "application/ecmascript", "text/jscript", "module",
}


@dataclass
class Snippet:
    path: str
    line: int
    kind: str
    code: str


class ScriptParser(HTMLParser):
    """HTMLParser excludes commented markup and keeps script data as raw text."""

    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.snippets = []
        self.sources = []
        self._script = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        line = self.getpos()[0]
        if tag == "script":
            script_type = (attributes.get("type") or "").strip().lower()
            # MIME parameters do not change the language of a classic script.
            script_type = script_type.split(";", 1)[0].strip()
            kind = "module" if script_type == "module" else "script"
            if script_type not in SCRIPT_TYPES:
                self._script = None
            elif "src" in attributes:
                self.sources.append((attributes["src"] or "", kind))
                self._script = None
            else:
                self._script = Snippet(self.path, line, kind, "")
        for name, value in attrs:
            if name.startswith("on") and value:
                self.snippets.append(Snippet(self.path, line, "handler", value))

    def handle_data(self, data):
        if self._script is not None:
            self._script.code += data

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            if self._script.code.strip():
                self.snippets.append(self._script)
            self._script = None

    def close(self):
        super().close()
        # An unclosed script can swallow the remainder of the HTML document.
        if self._script is not None:
            if self._script.code.strip():
                self.snippets.append(self._script)
            self._script = None


def html_files(root, include_archives=False):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".html":
            continue
        relative = path.relative_to(root)
        if {".git", "node_modules", "_vti_cnf"}.intersection(relative.parts):
            continue
        if include_archives or len(relative.parts) == 1 or relative.parts[0] in MAIN_DIRECTORIES:
            yield path


def collect(root, include_archives=False):
    snippets = []
    local_sources = set()
    pages = list(html_files(root, include_archives))
    for page in pages:
        parser = ScriptParser(page.relative_to(root).as_posix())
        parser.feed(page.read_text(encoding="utf-8", errors="replace"))
        parser.close()
        snippets.extend(parser.snippets)
        for source, kind in parser.sources:
            try:
                url = urlsplit(source)
            except ValueError:
                continue  # Malformed/missing resource URLs belong to the link audit.
            if url.scheme or url.netloc or not url.path:
                continue
            path = unquote(url.path)
            local = ((root / path.lstrip("/")) if path.startswith("/") else (page.parent / path)).resolve()
            if local.is_relative_to(root) and local.is_file():
                local_sources.add((local, kind))
    # Check the shared script even if a broken reference made it unreachable.
    shared_script = root / "js" / "app.js"
    if shared_script.is_file():
        local_sources.add((shared_script, "script"))
    for path, kind in sorted(local_sources):
        snippets.append(Snippet(path.relative_to(root).as_posix(), 1, kind,
                                path.read_text(encoding="utf-8", errors="replace")))
    return pages, local_sources, snippets


NODE_CHECKER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const snippets = JSON.parse(fs.readFileSync(0, 'utf8'));
const failures = [];
for (let index = 0; index < snippets.length; index++) {
    const {kind, code} = snippets[index];
    const name = `audit-snippet-${index}`;
    try {
        if (kind === 'module') {
            new vm.SourceTextModule(code, {identifier: name});
        } else {
            // Inline event attributes execute in a function and may use return.
            const script = kind === 'handler' ? `function handler(event) {\n${code}\n}` : code;
            new vm.Script(script, {filename: name});
        }
    } catch (error) {
        const match = String(error.stack).match(new RegExp(name + ':(\\d+)'));
        const line = match ? Math.max(1, Number(match[1]) - (kind === 'handler' ? 1 : 0)) : 1;
        failures.push({index, line, message: error.message});
    }
}
process.stdout.write(JSON.stringify(failures));
"""


def check(snippets):
    groups = {}
    for snippet in snippets:
        groups.setdefault((snippet.kind, snippet.code), []).append(snippet)
    unique = [{"kind": kind, "code": code} for kind, code in groups]
    process = subprocess.run(
        ["node", "--experimental-vm-modules", "--no-warnings", "-e", NODE_CHECKER],
        input=json.dumps(unique), text=True, capture_output=True, check=True,
    )
    failures = []
    locations = list(groups.values())
    for error in json.loads(process.stdout):
        for snippet in locations[error["index"]]:
            failures.append({
                "path": snippet.path,
                "line": snippet.line + error["line"] - 1,
                "kind": snippet.kind,
                "message": error["message"],
            })
    return len(unique), sorted(failures, key=lambda item: (item["path"], item["line"]))


def main(argv=None):
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments.add_argument("--include-archives", action="store_true")
    arguments.add_argument("--json", action="store_true", help="Emit a machine-readable result")
    args = arguments.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        arguments.error("--root must be an existing directory")
    pages, files, snippets = collect(root, args.include_archives)
    try:
        unique, failures = check(snippets)
    except FileNotFoundError:
        print("Node.js 18+ is required; install Node.js and rerun the check.", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(error.stderr, file=sys.stderr)
        return 2
    result = {"html_files": len(pages), "local_scripts": len(files),
              "snippets": len(snippets), "unique_snippets": unique, "failures": failures}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Checked {len(pages)} HTML files, {len(files)} local scripts and "
              f"{len(snippets)} active snippets ({unique} unique).")
        for failure in failures:
            print(f"{failure['path']}:{failure['line']}: {failure['message']} ({failure['kind']})")
        print(f"JavaScript syntax: {'FAIL' if failures else 'PASS'} ({len(failures)} errors).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
