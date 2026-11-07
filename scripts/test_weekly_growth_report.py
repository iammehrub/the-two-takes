import csv
import tempfile
import unittest
from pathlib import Path

from weekly_growth_report import analyze, build_report, duration_seconds, fmt_duration


class GrowthReportTests(unittest.TestCase):
    def test_duration_parses_studio_formats(self):
        self.assertEqual(duration_seconds("1:23"), 83.0)
        self.assertEqual(duration_seconds("1:02:03"), 3723.0)
        self.assertEqual(duration_seconds("83"), 83.0)
        self.assertIsNone(duration_seconds("N/A"))
        self.assertIsNone(duration_seconds("1:75"))

    def test_duration_formats_for_report(self):
        self.assertEqual(fmt_duration(83), "1:23")
        self.assertEqual(fmt_duration(3723), "1:02:03")
        self.assertEqual(fmt_duration(None), "not available in this export")

    def test_metrics_use_correct_weights(self):
        rows = [
            {
                "Video title": "Practise Ordering Food in English",
                "Views": "100",
                "Impressions": "100",
                "Impressions click-through rate": "2%",
                "Average view duration": "1:00",
                "Subscribers": "1",
                "Intro retention": "40%",
            },
            {
                "Video title": "Restaurant English Conversation",
                "Views": "300",
                "Impressions": "900",
                "Impressions click-through rate": "10%",
                "Average view duration": "2:00",
                "Subscribers": "3",
                "Intro retention": "60%",
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "studio.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

            videos, stats, columns = analyze(path)

        self.assertEqual(len(videos), 2)
        self.assertEqual(len(stats), 1)
        category = stats[0]
        self.assertAlmostEqual(category["avg_duration"], 105.0)
        self.assertAlmostEqual(category["avg_ctr"], 9.2)
        self.assertAlmostEqual(category["avg_retention30"], 55.0)
        self.assertEqual(category["views"], 400)
        self.assertEqual(category["impressions"], 1000)
        self.assertEqual(category["subs"], 4)
        report = build_report(videos, stats, columns)
        self.assertIn("1:45", report)
        self.assertIn("9.20%", report)

    def test_missing_metrics_remain_unavailable(self):
        rows = [{"Video title": "A simple English lesson", "Views": "10"}]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "studio.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            videos, stats, columns = analyze(path)
            report = build_report(videos, stats, columns)

        self.assertIsNone(videos[0]["avg_duration"])
        self.assertIsNone(stats[0]["avg_ctr"])
        self.assertIn("not available in this export", report)
        self.assertIsNone(columns["ctr"])


if __name__ == "__main__":
    unittest.main()
