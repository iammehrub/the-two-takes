"""Unit tests for the command-center run summary (no network access required)."""
import unittest
from datetime import datetime, timedelta, timezone

from scripts.update_notion_command_center import latest_runs_by_workflow, seven_day_run_stats


def run(path, created_at, *, status="completed", conclusion="success", run_number=1):
    return {
        "path": path,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": created_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "conclusion": conclusion,
        "run_number": run_number,
    }


class WorkflowSummaryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)

    def test_latest_run_is_kept_per_workflow(self):
        older = run(".github/workflows/daily-podcast.yml", self.now - timedelta(hours=2), run_number=10)
        newer = run(".github/workflows/daily-podcast.yml", self.now - timedelta(minutes=10), conclusion="failure", run_number=11)
        other = run(".github/workflows/youtube-analytics.yml", self.now - timedelta(minutes=5), conclusion="success", run_number=3)

        results = latest_runs_by_workflow([older, other, newer])

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["path"], ".github/workflows/youtube-analytics.yml")
        self.assertEqual(results[1]["run_number"], 11)

    def test_seven_day_stats_count_outcomes_and_ignore_older_runs(self):
        runs = [
            run("success.yml", self.now - timedelta(hours=1), conclusion="success"),
            run("failure.yml", self.now - timedelta(hours=2), conclusion="failure"),
            run("active.yml", self.now - timedelta(hours=3), status="in_progress", conclusion=""),
            run("cancelled.yml", self.now - timedelta(hours=4), conclusion="cancelled"),
            run("old.yml", self.now - timedelta(days=8), conclusion="failure"),
        ]

        stats = seven_day_run_stats(runs, now=self.now)

        self.assertEqual(stats, {
            "succeeded": 1,
            "failed": 1,
            "active": 1,
            "cancelled": 1,
            "other": 0,
        })

    def test_failed_conclusions_other_than_failure_are_counted(self):
        runs = [
            run("timeout.yml", self.now - timedelta(hours=1), conclusion="timed_out"),
            run("startup.yml", self.now - timedelta(minutes=30), conclusion="startup_failure"),
        ]

        stats = seven_day_run_stats(runs, now=self.now)

        self.assertEqual(stats["failed"], 2)


if __name__ == "__main__":
    unittest.main()
