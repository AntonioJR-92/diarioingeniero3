from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import unittest


IBERIA = Path(__file__).resolve().parents[1] / "viajes" / "iberia"


class OverviewParser(HTMLParser):
    def __init__(self, trip):
        super().__init__()
        self.cover_name = f"/mapas/m{trip:02d}.jpg"
        self.cover = None
        self.summary = []
        self.map_started = False
        self.targets = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and attrs.get("src", "").endswith(self.cover_name):
            self.cover = attrs
        if tag == "svg" and self.cover:
            self.map_started = True
        if tag == "a" and self.map_started and "aria-label" in attrs:
            href = attrs.get("href") or attrs.get("xlink:href")
            if href:
                self.targets[attrs["aria-label"]] = Path(urlsplit(href).path).name

    def handle_data(self, text):
        if self.cover and not self.map_started:
            self.summary.append(text)


def parse_overview(trip, language):
    page = OverviewParser(trip)
    page.feed((IBERIA / f"viajes{trip}_iberia_{language}.html").read_text(encoding="utf-8"))
    return page


class IberiaOverviewTest(unittest.TestCase):
    def test_completed_summaries_are_next_to_the_correct_cover(self):
        for number in range(10, 31):
            for lang, alternative in [("es", "Mapa general"), ("en", "Overview map")]:
                with self.subTest(trip=number, language=lang):
                    page = parse_overview(number, lang)
                    self.assertIsNotNone(page.cover)
                    self.assertTrue(page.cover["alt"].startswith(alternative))
                    self.assertGreater(len(" ".join(page.summary).split()), 30)

    def test_toledo_map_matches_the_southeastern_and_northwestern_routes(self):
        for lang in ("es", "en"):
            with self.subTest(language=lang):
                page = parse_overview(10, lang)
                for place, day in [("Consuegra", 4), ("Talavera", 5)]:
                    matches = [href for label, href in page.targets.items() if place in label]
                    self.assertEqual(matches, [f"viajes10_{day}_iberia_{lang}.html"])


if __name__ == "__main__":
    unittest.main()
