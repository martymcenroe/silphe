"""Two sessions in the same second must not share a file — issue #80.

The session filename carries a whole-second stamp, so these tests pin the clock
to a single second and check that sessions still land in files of their own.
Pinning is the point: without it the tests pass on a fast machine by accident
and stop testing anything.
"""

import glob
import json
import os

import pytest

from silphe import core
from silphe.core import Recorder


@pytest.fixture(autouse=True)
def recordings(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path / "recordings"))
    monkeypatch.setattr(core, "_issued_session_paths", set())
    return tmp_path / "recordings"


@pytest.fixture()
def frozen_clock(monkeypatch):
    """Every session in this test begins in the same second."""
    monkeypatch.setattr(core.time, "time", lambda: 1787617756.5)


def sessions_in(d):
    return sorted(glob.glob(os.path.join(str(d), "session-*.jsonl")))


def records_in(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def test_reopening_in_the_same_second_names_a_different_file(frozen_clock, recordings):
    rec = Recorder(device="mouse", player=None)
    first = rec.path
    rec.open_session()
    assert rec.path != first
    rec.close()


def test_two_recorders_in_the_same_second_do_not_share_a_file(frozen_clock, recordings):
    a = Recorder(device="mouse", player=None)
    b = Recorder(device="mouse", player=None)
    assert a.path != b.path
    a.close()
    b.close()


def test_records_from_two_same_second_sessions_stay_separate(frozen_clock, recordings):
    """The actual damage: appending into one file silently merged two sessions."""
    a = Recorder(device="mouse", player=None)
    a.write({"kind": "hold"})
    a.close()

    b = Recorder(device="mouse", player=None)
    b.write({"kind": "acquire"})
    b.close()

    files = sessions_in(recordings)
    assert len(files) == 2, "the two sessions landed in one file"
    assert [r["kind"] for r in records_in(a.path)] == ["hold"]
    assert [r["kind"] for r in records_in(b.path)] == ["acquire"]


def test_a_reopened_session_keeps_the_earlier_records_in_their_own_file(frozen_clock, recordings):
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    first = rec.path
    rec.open_session()
    rec.write({"kind": "acquire"})
    rec.close()

    assert [r["kind"] for r in records_in(first)] == ["hold"]
    assert [r["kind"] for r in records_in(rec.path)] == ["acquire"]


# ---- the shape of the name has to survive, because two readers parse it ----

def test_the_name_keeps_its_documented_shape(frozen_clock, recordings):
    """`session-<epoch>-<device>.jsonl`, with no suffix bolted on."""
    rec = Recorder(device="mouse", player=None)
    rec.open_session()                                     # force the collision path
    parts = os.path.basename(rec.path)[:-len(".jsonl")].split("-")
    assert parts[0] == "session"
    assert parts[1].isdigit()
    assert parts[2] == "mouse"
    assert len(parts) == 3, "a suffix would break analysis.py's filename ordering"
    rec.close()


def test_arc_reads_the_stamp_and_device_back_out(frozen_clock, recordings):
    """Mirrors arc.load_sessions' parse, which is the reason for the shape."""
    rec = Recorder(device="trackpad", player=None)
    rec.open_session()
    parts = os.path.basename(rec.path)[:-6].split("-")
    assert int(parts[1]) >= 1787617756
    assert parts[2] == "trackpad"
    rec.close()


def test_the_disambiguated_name_sorts_after_the_one_it_follows(frozen_clock, recordings):
    """analysis.load_all orders sessions by sorting filenames, so the later
    session must sort later. A `-2` suffix would sort before, because `-` comes
    before `.`."""
    a = Recorder(device="mouse", player=None)
    a.write({"kind": "hold"})
    b = Recorder(device="mouse", player=None)
    b.write({"kind": "acquire"})
    a.close()
    b.close()

    assert sorted([a.path, b.path]) == [a.path, b.path]
    assert sessions_in(recordings) == [a.path, b.path]


def test_the_stamp_only_advances_as_far_as_it_must(frozen_clock, recordings):
    """Three sessions in one second take that second and the two after it —
    not an arbitrary jump."""
    recs = [Recorder(device="mouse", player=None) for _ in range(3)]
    stamps = [int(os.path.basename(r.path).split("-")[1]) for r in recs]
    assert stamps == [1787617756, 1787617757, 1787617758]
    for r in recs:
        r.close()


def test_an_existing_file_on_disk_is_not_reused(frozen_clock, recordings):
    """A file from an earlier run in the same second still counts as taken,
    even though this process never issued it."""
    recordings.mkdir(parents=True, exist_ok=True)
    squatter = recordings / "session-1787617756-mouse.jsonl"
    squatter.write_text('{"kind": "from-an-earlier-run"}\n', encoding="utf-8")

    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    rec.close()

    assert rec.path != str(squatter)
    assert [r["kind"] for r in records_in(squatter)] == ["from-an-earlier-run"]


def test_different_players_are_unaffected(frozen_clock, recordings):
    """Separate directories were never in conflict; the same second is fine."""
    a = Recorder(device="mouse", player=None)
    b = Recorder(device="mouse", player="Rebecca")
    assert os.path.basename(a.path) == os.path.basename(b.path)
    assert os.path.dirname(a.path) != os.path.dirname(b.path)
    a.close()
    b.close()


def test_the_ordinary_case_is_still_the_current_second(recordings):
    """No frozen clock: one session, stamped now, no advancing."""
    import time as real_time

    before = int(real_time.time())
    rec = Recorder(device="mouse", player=None)
    after = int(real_time.time())
    stamp = int(os.path.basename(rec.path).split("-")[1])
    assert before <= stamp <= after
    rec.close()
