import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import recommend  # noqa: E402
from recommend import recommend as recommend_for  # noqa: E402


class RecommendTests(unittest.TestCase):
    def test_returns_top_ranked_intervention_for_outcome(self):
        self.assertEqual(recommend_for("fatigue"), "Yoga")
        self.assertEqual(recommend_for("falls"), "Tai chi")

    def test_outcome_match_ignores_case_and_whitespace(self):
        self.assertEqual(recommend_for("  Chronic Pain "), "Acupuncture")

    def test_unknown_outcome_raises_value_error(self):
        with self.assertRaises(ValueError):
            recommend_for("not a real outcome")

    def test_every_ranked_outcome_maps_to_its_intervention(self):
        for _rank, intervention, outcome in recommend._RANKING:
            with self.subTest(outcome=outcome):
                self.assertEqual(recommend_for(outcome), intervention)

    def test_constants_match_ranking_csv(self):
        with (ROOT / "analysis" / "ranking.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        expected = tuple((int(r["rank"]), r["intervention"], r["outcome"]) for r in rows)
        self.assertEqual(recommend._RANKING, expected)


if __name__ == "__main__":
    unittest.main()
