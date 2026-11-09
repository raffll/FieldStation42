"""raffll mod: random_show sequences with "sequence_switch": "season" switch show at a season
boundary (checked at slot start) and resume a show where it stopped."""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_ffmpeg_stub = MagicMock()
_ffmpeg_stub.probe = MagicMock()
sys.modules.setdefault("ffmpeg", _ffmpeg_stub)

_moviepy_stub = MagicMock()
sys.modules.setdefault("moviepy", _moviepy_stub)
sys.modules.setdefault("moviepy.editor", _moviepy_stub)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fs42.sequence import NamedSequence  # noqa: E402
from fs42.sequence_api import SequenceAPI  # noqa: E402


def _eps(show, *codes):
    return [f"/m/{show}/Season {int(c[1:3])}/{show} - {c}.mp4" for c in codes]


class TestSeasonSwitch(unittest.TestCase):
    STATION = {"network_name": "stn"}
    SEQ = "seq"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        patcher = patch("fs42.sequence_io.StationManager")
        station_manager = patcher.start()
        station_manager.return_value.server_conf = {"db_path": os.path.join(self.tmp, "test.db")}
        self.addCleanup(patcher.stop)
        # deterministic: always take the first candidate (ShowA before ShowB)
        choice = patch("fs42.sequence_api.random.choice", lambda xs: sorted(xs)[0])
        choice.start()
        self.addCleanup(choice.stop)

        from fs42.sequence_io import SequenceIO
        self.sio = SequenceIO()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _put_child(self, show, files):
        ns = NamedSequence("stn", self.SEQ, f"shows/{show}", 0.0, 1.0, 0, files, initialized=True)
        ns.parent_tag = "shows"
        self.sio.put_sequence("stn", ns)

    def _next(self, slot_start=True, switch_on="season"):
        entry = SequenceAPI.get_next_in_sequence(
            self.STATION, self.SEQ, "shows", switch_on=switch_on, slot_start=slot_start
        )
        return os.path.splitext(os.path.basename(entry.fpath))[0]

    def test_switches_at_season_boundary_and_resumes(self):
        self._put_child("ShowA", _eps("ShowA", "S01E01", "S01E02", "S02E01", "S02E02"))
        self._put_child("ShowB", _eps("ShowB", "S01E01", "S01E02"))
        played = [self._next() for _ in range(7)]
        self.assertEqual(played, [
            "ShowA - S01E01", "ShowA - S01E02",
            "ShowB - S01E01", "ShowB - S01E02",   # A reached season 2 -> switch
            "ShowA - S02E01", "ShowA - S02E02",   # B ended -> A resumes with season 2
            "ShowB - S01E01",                     # A ended -> B restarts
        ])

    def test_season_started_mid_slot_is_rewound(self):
        self._put_child("ShowA", _eps("ShowA", "S01E01", "S01E02", "S02E01", "S02E02"))
        self._put_child("ShowB", _eps("ShowB", "S01E01", "S01E02", "S01E03"))
        played = [
            self._next(True), self._next(False), self._next(False),  # slot 1: A crosses into S02
            self._next(True), self._next(False), self._next(False),  # slot 2: switch to B
            self._next(True),                                        # slot 3: B ended -> A
        ]
        self.assertEqual(played, [
            "ShowA - S01E01", "ShowA - S01E02", "ShowA - S02E01",
            "ShowB - S01E01", "ShowB - S01E02", "ShowB - S01E03",
            "ShowA - S02E01",                     # season 2 plays from its first episode
        ])

    def test_single_show_just_continues(self):
        self._put_child("ShowA", _eps("ShowA", "S01E01", "S02E01", "S02E02"))
        played = [self._next() for _ in range(3)]
        self.assertEqual(played, ["ShowA - S01E01", "ShowA - S02E01", "ShowA - S02E02"])

    def test_without_option_shows_run_to_the_end(self):
        self._put_child("ShowA", _eps("ShowA", "S01E01", "S02E01", "S02E02"))
        self._put_child("ShowB", _eps("ShowB", "S01E01"))
        played = [self._next(switch_on=None) for _ in range(4)]
        self.assertEqual(played, ["ShowA - S01E01", "ShowA - S02E01", "ShowA - S02E02", "ShowB - S01E01"])

    def test_season_of(self):
        self.assertEqual(SequenceAPI._season_of("/m/X/Season 3/X - S03E04.mkv"), "3")
        self.assertEqual(SequenceAPI._season_of("/m/X/Specials/X - S00E07.mkv"), "0")
        self.assertEqual(SequenceAPI._season_of("/m/X/Season 01 Classic Cuts/ep1.mkv"), "Season 01 Classic Cuts")


if __name__ == "__main__":
    unittest.main()
