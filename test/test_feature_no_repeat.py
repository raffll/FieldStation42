"""raffll mod: features are picked by plays per file (over all tag folders that link the
file), and a slot skips files the station aired in the last 24 h unless nothing else fits."""

import datetime
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_ffmpeg_stub = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)
_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.catalog import ShowCatalog  # noqa: E402
from fs42.catalog_entry import CatalogEntry  # noqa: E402
from fs42.liquid_schedule import LiquidSchedule  # noqa: E402

PRIME = "movie/action+comedy/prime"
LATE = "movie/action/prime+late"


def _entry(name, tag, count=0, ctype="feature"):
    e = CatalogEntry(f"catalog/ch1/{tag}/{name}.mkv", 5400, tag, [], count, content_type=ctype)
    e.realpath = f"/mnt/nas/Movies/{name}.mkv"  # same file under every tag folder
    return e


class TestPickFeature(unittest.TestCase):
    def setUp(self):
        self.cat = ShowCatalog({"network_name": "stn", "network_type": "standard"}, load=False)
        self.cat.clip_index = {
            PRIME: [_entry("Commando", PRIME), _entry("Airplane", PRIME)],
            LATE: [_entry("Commando", LATE), _entry("Cobra", LATE)],
        }
        self.cat._plays = None

    def _pick(self, tag, recent=None):
        return os.path.basename(self.cat.file_key(self.cat._pick_feature(list(self.cat.clip_index[tag]), recent)))

    def test_plays_count_per_file_across_tags(self):
        # Commando played from the prime pool -> the late pool must take Cobra
        with patch("fs42.catalog.random.choice", lambda xs: [x for x in xs if "Commando" in x.path][0] if any("Commando" in x.path for x in xs) else xs[0]):
            self.assertEqual(self._pick(PRIME), "Commando.mkv")
            self.assertEqual(self._pick(LATE), "Cobra.mkv")

    def test_stored_counts_are_summed(self):
        self.cat.clip_index[PRIME][0].count = 1  # Commando aired once via the prime folder
        self.cat._plays = None
        self.assertEqual(self._pick(LATE), "Cobra.mkv")

    def test_recent_files_are_skipped(self):
        recent = {"/mnt/nas/Movies/Cobra.mkv"}
        self.cat.clip_index[LATE][0].count = 5  # Commando played a lot, Cobra aired recently
        self.cat._plays = None
        self.assertEqual(self._pick(LATE, recent), "Commando.mkv")

    def test_repeats_when_everything_is_recent(self):
        recent = {"/mnt/nas/Movies/Cobra.mkv", "/mnt/nas/Movies/Commando.mkv"}
        self.assertIn(self._pick(LATE, recent), ("Cobra.mkv", "Commando.mkv"))


class TestRecentIndex(unittest.TestCase):
    def test_window_is_24_hours_back(self):
        sched = LiquidSchedule.__new__(LiquidSchedule)
        idx = {}
        t0 = datetime.datetime(2026, 11, 15, 20, 30)
        LiquidSchedule._register_recent(idx, SimpleNamespace(content=_entry("Commando", PRIME), start_time=t0))
        LiquidSchedule._register_recent(idx, SimpleNamespace(content=_entry("Ad", "commercial", ctype="commercial"), start_time=t0))
        LiquidSchedule._register_recent(idx, SimpleNamespace(content=[_entry("Clip", "clips")], start_time=t0))
        self.assertEqual(list(idx), ["/mnt/nas/Movies/Commando.mkv"])
        self.assertEqual(sched._recent_files(idx, t0 + datetime.timedelta(hours=2)), {"/mnt/nas/Movies/Commando.mkv"})
        self.assertEqual(sched._recent_files(idx, t0 + datetime.timedelta(hours=25)), set())


if __name__ == "__main__":
    unittest.main()
