import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from recommend import INTERVENTION_RANK, OUTCOME_INTERVENTIONS, recommend  # noqa: E402


class RecommendTests(unittest.TestCase):
    def test_returns_intervention_for_outcome(self):
        self.assertEqual(recommend("fatigue"), "Yoga")
        self.assertEqual(recommend("cognitive decline"), "Hearing aids")

    def test_every_outcome_maps_to_its_study(self):
        for outcome, interventions in OUTCOME_INTERVENTIONS.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(recommend(outcome), interventions[0])

    def test_lookup_ignores_case_and_surrounding_space(self):
        self.assertEqual(recommend("  Fatigue "), "Yoga")

    def test_best_rank_wins_among_several_candidates(self):
        original = OUTCOME_INTERVENTIONS.copy()
        try:
            OUTCOME_INTERVENTIONS["test outcome"] = ("Tai chi", "Yoga", "Hydration reminders")
            self.assertEqual(recommend("test outcome"), "Yoga")
        finally:
            OUTCOME_INTERVENTIONS.clear()
            OUTCOME_INTERVENTIONS.update(original)

    def test_unknown_outcome_raises(self):
        with self.assertRaises(ValueError):
            recommend("baldness")

    def test_empty_outcome_raises(self):
        with self.assertRaises(ValueError):
            recommend("")


class ConstantsMatchDataTests(unittest.TestCase):
    """Guard against drift: the constants must agree with the source files."""

    def test_ranks_match_ranking_csv(self):
        with open(ROOT / "analysis" / "ranking.csv", newline="", encoding="utf-8") as f:
            expected = {row["intervention"]: int(row["rank"]) for row in csv.DictReader(f)}
        self.assertEqual(INTERVENTION_RANK, expected)

    def test_outcomes_match_findings(self):
        with open(ROOT / "data" / "findings.json", encoding="utf-8") as f:
            records = json.load(f)
        expected = {}
        for rec in records:
            expected.setdefault(rec["outcome"], set()).add(rec["intervention"])
        self.assertEqual({k: set(v) for k, v in OUTCOME_INTERVENTIONS.items()}, expected)


if __name__ == "__main__":
    unittest.main()
