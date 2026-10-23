"""Regression tests for fixed-position captions in the full-episode renderer."""

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_renderer_without_network_dependencies():
    """The tested caption writer needs no network or numerical package calls."""
    fake_audio = types.ModuleType("audio_enhancements")
    fake_audio.build_chapters = lambda *_args, **_kwargs: []
    fake_audio.generate_music_bed = lambda *_args, **_kwargs: None
    fake_audio.select_short_windows = lambda *_args, **_kwargs: []
    fake_requests = types.ModuleType("requests")
    fake_app = types.ModuleType("build_podcast")
    with patch.dict(sys.modules, {
        "audio_enhancements": fake_audio,
        "requests": fake_requests,
        "build_podcast": fake_app,
    }):
        sys.modules.pop("production_upgrade", None)
        return importlib.import_module("production_upgrade")


class VideoPresentationTests(unittest.TestCase):
    def test_captions_are_timed_and_positioned_under_the_matching_host(self):
        renderer = load_renderer_without_network_dependencies()
        scratch = Path(__file__).resolve().parents[1] / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            work = Path(tmp)
            (work / "tts_segments.json").write_text(
                json.dumps([
                    {"speaker": "Himel", "text": "This is Himel speaking now.", "start": 1.0, "end": 3.0},
                    {"speaker": "Niha", "text": "And Niha answers him clearly.", "start": 3.2, "end": 5.0},
                ]),
                encoding="utf-8",
            )
            renderer.app = types.SimpleNamespace(WORK=work)

            srt_path = renderer.make_srt("unused", 8.0)
            ass = (work / "captions.ass").read_text(encoding="utf-8")
            srt = srt_path.read_text(encoding="utf-8")

        self.assertIn("00:00:00,970 -->", srt)
        self.assertIn("00:00:03,170 -->", srt)
        self.assertRegex(ass, r"Dialogue: 0,0:00:00\.97,0:00:03\.03,Himel.*\\pos\(470,775\)")
        self.assertRegex(ass, r"Dialogue: 0,0:00:03\.17,0:00:05\.03,Niha.*\\pos\(1450,775\)")


if __name__ == "__main__":
    unittest.main()
