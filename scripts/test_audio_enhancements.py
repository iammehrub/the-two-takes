import tempfile
import wave
import unittest
from pathlib import Path

import numpy as np

from scripts.audio_enhancements import build_chapters, generate_music_bed


class AudioEnhancementTests(unittest.TestCase):
    def test_music_bed_is_stereo_and_has_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "music.wav"
            generate_music_bed(3.5, output, sample_rate=8000)

            self.assertTrue(output.exists())
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getframerate(), 8000)
                self.assertAlmostEqual(wav.getnframes() / 8000, 3.5, places=2)
                raw = wav.readframes(wav.getnframes())

            samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
            rms = float(np.sqrt(np.mean(samples * samples)))
            self.assertGreater(rms, 10.0, "Music bed should not be silent.")
            self.assertLess(rms, 5000.0, "Music bed should remain safely quiet.")

    def test_music_bed_rejects_invalid_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                generate_music_bed(0, Path(tmp) / "bad.wav", sample_rate=8000)

    def test_chapters_start_at_zero_and_include_major_sections(self):
        turns = [
            {"start": 0.0, "turn_type": "hook"},
            {"start": 19.0, "turn_type": "story"},
            {"start": 125.0, "turn_type": "language_tip"},
            {"start": 290.0, "turn_type": "practice"},
            {"start": 520.0, "turn_type": "recap"},
        ]
        chapters = build_chapters(turns, 600.0)
        self.assertGreaterEqual(len(chapters), 4)
        self.assertTrue(chapters[0].startswith("00:00 "))
        self.assertTrue(any("phrases" in item.lower() for item in chapters))
        self.assertTrue(any("practice" in item.lower() for item in chapters))
        self.assertTrue(any("review" in item.lower() for item in chapters))


if __name__ == "__main__":
    unittest.main()
