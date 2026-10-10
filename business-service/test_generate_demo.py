"""Unit tests for the approval-only content generator."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import generate_demo


class GeneratorTests(unittest.TestCase):
    def profile(self):
        return {
            "business_name": "North Star Cafe", "industry": "cafe",
            "location": "Dhaka", "audience": "students",
            "primary_offer": "tea and snacks", "primary_channel": "Facebook",
            "brand_facts": ["Fictional sample profile"],
            "avoid_claims": ["unverified prices"],
        }

    def test_seven_distinct_drafts_require_approval(self):
        items = generate_demo.build_items(self.profile(), date(2026, 10, 12))
        self.assertEqual(len(items), 7)
        self.assertEqual(len({x["caption_draft"] for x in items}), 7)
        self.assertEqual(items[0]["date"], "2026-10-12")
        self.assertEqual(items[-1]["date"], "2026-10-18")
        self.assertTrue(all(x["status"] == generate_demo.STATUS for x in items))
        self.assertTrue(all("North Star Cafe" in x["caption_draft"] for x in items))
        self.assertTrue(all("unverified prices" in x["claims_to_avoid"] for x in items))

    def test_missing_required_profile_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps({"business_name": "Incomplete"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing required profile fields"):
                generate_demo.load_profile(path)

    def test_fact_lists_must_be_arrays(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            data = self.profile()
            data["avoid_claims"] = "not-a-list"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON array"):
                generate_demo.load_profile(path)

    def test_markdown_discloses_draft_only_mode(self):
        profile = self.profile()
        items = generate_demo.build_items(profile, date(2026, 10, 12))
        md = generate_demo.render_markdown(profile, items, date(2026, 10, 12), "template-only")
        self.assertIn("NO POSTS HAVE BEEN PUBLISHED", md)
        self.assertIn("HUMAN APPROVAL REQUIRED", md)
        self.assertIn("not fact-checked research", md)

    def test_ai_without_key_falls_back_without_network(self):
        items = generate_demo.build_items(self.profile(), date(2026, 10, 12))
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            changed, mode = generate_demo.improve_with_free_ai(self.profile(), items)
        self.assertEqual(mode, "template-fallback-no-api-key")
        self.assertEqual(changed[0]["caption_draft"], items[0]["caption_draft"])

    def test_ai_bad_response_falls_back(self):
        items = generate_demo.build_items(self.profile(), date(2026, 10, 12))
        fake_response = type("Response", (), {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
            "read": lambda self: b'{"choices":[{"message":{"content":"not-json"}}]}',
        })()
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=fake_response
        ):
            changed, mode = generate_demo.improve_with_free_ai(self.profile(), items)
        self.assertEqual(mode, "template-fallback-ai-unavailable")
        self.assertEqual(len(changed), 7)


if __name__ == "__main__":
    unittest.main()
