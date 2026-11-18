"""Regression tests for browser-style paths, parsing boundaries and CI baselines."""

import importlib.util
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "audit_site", Path(__file__).resolve().parents[1] / "tools" / "audit_site.py")
audit_site = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_site
SPEC.loader.exec_module(audit_site)


class StaticSiteAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, content=""):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_nested_links_queries_unicode_fragments_and_named_anchors(self):
        self.write("index.html", '<a href="../../viajes/page_es.html?mode=1#caf%C3%A9">Go</a>')
        self.write("viajes/page_es.html", '<html lang="es"><a name="café"></a>'
                   '<img src="..\\imags\\foto%20uno.jpg?size=2"><a href="../index.html">Home</a></html>')
        self.write("imags/foto uno.jpg")
        self.assertEqual(audit_site.audit(self.root)["issues"], [])

    def test_comments_scripts_external_urls_and_css_strings_are_not_links(self):
        self.write("index.html", '''<!-- <img src="missing-comment.jpg"> -->
            <script>const sample = '<img src="missing-script.jpg">';</script>
            <a href="mailto:test@example.com">Email</a><a href="javascript:void(0)">Action</a>
            <img src="data:image/png;base64,AA=="><img src="https://example.com/image.jpg">
            <link rel="stylesheet" href="css/main.css">
            <style>/* url(missing-inline.png) */ .a { content: "url(missing-string.png)"; }</style>''')
        self.write("css/main.css", '/* url(missing.css) */ .a { content: "url(missing.png)"; }')
        self.assertEqual(audit_site.audit(self.root)["issues"], [])

    def test_css_imports_and_srcset_follow_actual_candidates(self):
        self.write("index.html", '<link rel="stylesheet" href="css/main.css">'
                   '<img srcset="data:image/png;base64,AA== 1x, imags/photo.jpg 2x">')
        self.write("css/main.css", '@import "nested.css"; .x { background: url(../imags/photo.jpg); }')
        self.write("css/nested.css", '.x { background: url("../imags/missing.png"); }')
        self.write("imags/photo.jpg")
        report = audit_site.audit(self.root)
        self.assertEqual(report["summary"]["css_files"], 2)
        self.assertEqual([(x["file"], x["url"]) for x in report["issues"]],
                         [("css/nested.css", "../imags/missing.png")])

    def test_active_and_disabled_missing_references_are_distinguished(self):
        self.write("index.html", '<li class="disabled"><a href="future.html">Soon</a></li>'
                   '<a href="broken.html">Broken</a><a aria-disabled="true" href="planned.html">Later</a>')
        report = audit_site.audit(self.root)
        self.assertEqual(len(report["issues"]), 3)
        self.assertEqual([x["url"] for x in audit_site.new_issues(report)], ["broken.html"])
        self.write("index.html", '<a href="future.html">Published</a>')
        self.assertEqual([x["url"] for x in audit_site.new_issues(audit_site.audit(self.root), report)],
                         ["future.html"])

    def test_svg_map_links_and_image_resources_are_checked(self):
        self.write("index.html", '<svg><path id="province"></path>'
                   '<a xlink:href="viajes/place_es.html#details"><use xlink:href="#province"></use></a>'
                   '<image xlink:href="imags/map.png"></image>'
                   '<a xlink:href="viajes/missing.html">Missing destination</a></svg>')
        self.write("viajes/place_es.html", '<html lang="es"><p id="details">Place</p></html>')
        self.write("imags/map.png")
        issues = audit_site.audit(self.root)["issues"]
        self.assertEqual([(item["code"], item["url"]) for item in issues],
                         [("missing_file", "viajes/missing.html")])

    def test_detects_structural_and_dependency_regressions(self):
        self.write("page_en.html", '<html lang="es"><div id="repeat"></div><p id="repeat"></p>'
                   '<a href="#missing">Jump</a><script src="https://code.jquery.com/jquery-3.1.1.slim.min.js"></script>'
                   '<script src="https://code.jquery.com/jquery-3.6.0.js"></script>'
                   '<script src="https://example.com/bootstrap.min.js"></script>'
                   '<script src="https://other.example/bootstrap.js"></script></html>')
        report = audit_site.audit(self.root)
        self.assertEqual(Counter(x["code"] for x in report["issues"]),
                         {"duplicate_id": 1, "language_mismatch": 1,
                          "missing_fragment": 1, "duplicate_script": 2})

    def test_baseline_ignores_line_movement_but_detects_new_destination(self):
        self.write("index.html", '<a href="missing.html">Old</a>')
        baseline = audit_site.audit(self.root)
        self.write("index.html", '\n\n\n<a href="missing.html">Old</a><img src="new-missing.jpg">')
        report = audit_site.audit(self.root)
        self.assertEqual([x["url"] for x in audit_site.new_issues(report, baseline)], ["new-missing.jpg"])

    def test_baseline_rejects_more_copies_of_an_existing_problem(self):
        self.write("index.html", '<p id="repeat"></p><p id="repeat"></p>'
                   '<a href="missing.html">Old</a>')
        baseline = audit_site.audit(self.root)
        self.write("index.html", '<p id="repeat"></p><p id="repeat"></p><p id="repeat"></p>'
                   '<a href="missing.html">Old</a><a href="missing.html">New copy on the same line</a>')
        worsened = audit_site.new_issues(audit_site.audit(self.root), baseline)
        self.assertEqual({item["code"]: item["count"] for item in worsened},
                         {"duplicate_id": 3, "missing_file": 2})

    def test_main_scope_archive_scope_and_determinism(self):
        self.write("index.html", '<a href="blog/post_es.html">Post</a>')
        self.write("blog/post_es.html", '<html lang="es"></html>')
        self.write("lm_brianda_21/example.HTML", '<img src="missing.jpg">')
        self.write("css/demo.html", '<img src="missing.jpg">')
        self.assertEqual(audit_site.audit(self.root)["summary"]["html_files"], 2)
        self.assertEqual(audit_site.audit(self.root, True)["summary"]["html_files"], 4)
        self.assertEqual(json.dumps(audit_site.audit(self.root, True)),
                         json.dumps(audit_site.audit(self.root, True)))

    def test_local_base_and_external_base_use_document_url_rules(self):
        self.write("index.html", '<base href="/viajes/"><a href="post_es.html#entry">Post</a>')
        self.write("viajes/post_es.html", '<html lang="es"><a id="entry"></a></html>')
        self.assertEqual(audit_site.audit(self.root)["issues"], [])
        self.write("index.html", '<base href="https://example.com/"><img src="external.jpg">')
        self.assertEqual(audit_site.audit(self.root)["issues"], [])


if __name__ == "__main__":
    unittest.main()
