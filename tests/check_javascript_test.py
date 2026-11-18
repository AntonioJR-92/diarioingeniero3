"""Regression checks for real HTML/script boundary cases seen in this audit."""

import importlib.util
from pathlib import Path
import sys
import unittest

SPEC = importlib.util.spec_from_file_location(
    "check_javascript", Path(__file__).resolve().parents[1] / "tools" / "check_javascript.py"
)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def parse(html):
    parser = checker.ScriptParser("fixture.html")
    parser.feed(html)
    parser.close()
    return parser


class JavaScriptBoundaries(unittest.TestCase):
    def test_comments_data_and_external_inline_contents_are_not_executed(self):
        page = parse('<!-- <script>not valid JS!</script> -->'
                     '<script type="application/ld+json">{"name": "entry"}</script>'
                     '<script src="external.js">also not executed!</script>'
                     '<script>window.valid = true;</script>')
        self.assertEqual(len(page.snippets), 1)
        self.assertEqual(page.sources, [("external.js", "script")])
        self.assertEqual(checker.check(page.snippets)[1], [])

    def test_handlers_support_return_and_decoded_html_entities(self):
        page = parse('<a onclick="return 1 &lt; 2;">open</a>')
        self.assertEqual(checker.check(page.snippets)[1], [])

    def test_modules_allow_import_but_classic_scripts_do_not(self):
        page = parse('<script type="module">import thing from "./thing.js";</script>'
                     '<script>import thing from "./thing.js";</script>')
        errors = checker.check(page.snippets)[1]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["kind"], "script")

    def test_deduplication_reports_every_affected_location(self):
        page = parse('<script>const size = 300px;</script>\n'
                     '<script>const size = 300px;</script>')
        unique, errors = checker.check(page.snippets)
        self.assertEqual(unique, 1)
        self.assertEqual([error["line"] for error in errors], [1, 2])

    def test_missing_closing_tag_does_not_hide_embedded_markup(self):
        page = parse('<script>window.example = true;\n<div>lost content</div></script>')
        errors = checker.check(page.snippets)[1]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["line"], 2)


if __name__ == "__main__":
    unittest.main()
