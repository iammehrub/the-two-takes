"""Unit tests for the free local dialogue quality checker."""
import unittest

from dialogue_qc import evaluate_dialogue
from openai_pipeline import is_repeat_invitation


def sample_dialogue():
    beats = []
    types = ["hook", "question", "story", "follow_up", "language_tip", "practice"]
    for index in range(30):
        beats.append({
            "turn_index": index,
            "speaker": "Himel" if index % 2 == 0 else "Niha",
            "turn_type": types[index % len(types)],
            "text": (
                f"How would you describe your daily routine today number {index}?"
            ),
        })
    return beats


class DialogueQCTests(unittest.TestCase):
    def test_balanced_conversation_scores_well(self):
        report = evaluate_dialogue(sample_dialogue())
        self.assertGreaterEqual(report["score"], 90)
        self.assertEqual(report["host_turn_counts"]["Himel"], 15)
        self.assertEqual(report["host_turn_counts"]["Niha"], 15)

    def test_repeated_line_is_detected(self):
        beats = sample_dialogue()
        duplicate = dict(beats[0])
        duplicate["turn_index"] = len(beats)
        duplicate["speaker"] = "Niha"
        beats.append(duplicate)
        report = evaluate_dialogue(beats)
        self.assertEqual(report["repeated_line_count"], 1)
        self.assertLess(report["score"], 100)

    def test_repeat_pause_only_follows_learner_invitation(self):
        self.assertFalse(is_repeat_invitation("practice", "Listen to the phrase: take your time."))
        self.assertTrue(is_repeat_invitation("practice", "Now your turn. Repeat after me."))
        self.assertFalse(is_repeat_invitation("language_tip", "Now your turn."))
        
    def test_report_exposes_explainable_metrics(self):
        report = evaluate_dialogue(sample_dialogue())
        self.assertIn("question_count", report)
        self.assertIn("average_sentence_words", report)
        self.assertIn("warnings", report)
        self.assertEqual(report["review_type"],
                         "local heuristic; human listening review still required")


if __name__ == "__main__":
    unittest.main()
