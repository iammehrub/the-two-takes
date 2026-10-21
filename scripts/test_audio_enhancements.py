import tempfile
import wave
import unittest
from pathlib import Path

import numpy as np

from scripts.audio_enhancements import build_chapters, generate_music_bed, select_short_windows


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

    def test_short_windows_are_bounded_non_overlapping_and_start_on_speech(self):
        segments = []
        labels = {0: 'hook', 45: 'language_tip', 90: 'practice', 135: 'story'}
        for i in range(36):
            start = float(i * 5)
            segments.append({
                'start': start,
                'end': start + 5.0,
                'turn_index': i,
                'turn_type': labels.get(int(start), 'reaction'),
                'text': f'spoken segment {i}',
            })

        windows = select_short_windows(segments, 180.0, max_clips=3)
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows, sorted(windows, key=lambda item: item['start']))
        for window in windows:
            self.assertGreaterEqual(window['duration'], 18.0)
            self.assertLessEqual(window['duration'], 35.0)
            self.assertIn(window['start'], [item['start'] for item in segments])
            self.assertIn(window['end'], [item['end'] for item in segments])
        for previous, current in zip(windows, windows[1:]):
            self.assertGreaterEqual(current['start'] - previous['start'], 35.0)
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
