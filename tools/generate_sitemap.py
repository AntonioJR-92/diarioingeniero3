#!/usr/bin/env python3
"""Generate the sitemap from existing main-site pages, excluding teaching archives.

The default origin uses the public GitHub Pages deployment. Pass
--base-url explicitly when deploying a fork under another domain or subpath.
No modification dates or crawl frequencies are invented.
"""

import argparse
from pathlib import Path
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET

from audit_site import site_html_files


NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
DEFAULT_BASE_URL = "https://antoniojr-92.github.io/diarioingeniero3/"


def build(root, base_url):
    ET.register_namespace("", NAMESPACE)
    sitemap = ET.Element(f"{{{NAMESPACE}}}urlset")
    for path in sorted(site_html_files(root), key=lambda page: page.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        suffix = "" if relative == "index.html" else quote(relative, safe="/")
        item = ET.SubElement(sitemap, f"{{{NAMESPACE}}}url")
        ET.SubElement(item, f"{{{NAMESPACE}}}loc").text = base_url.rstrip("/") + "/" + suffix
    ET.indent(sitemap, space="  ")
    return ET.tostring(sitemap, encoding="unicode", xml_declaration=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--check", action="store_true", help="Check without rewriting sitemap.xml")
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.query or parsed.fragment:
        parser.error("--base-url must be an absolute HTTP(S) site URL without query or fragment")
    output = args.root / "sitemap.xml"
    expected = build(args.root, args.base_url)
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != expected:
            print("sitemap.xml is out of date; run python3 tools/generate_sitemap.py")
            return 1
        print("sitemap.xml matches the existing main-site pages.")
        return 0
    output.write_text(expected, encoding="utf-8")
    print(f"Updated sitemap.xml with {len(list(site_html_files(args.root)))} existing pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
