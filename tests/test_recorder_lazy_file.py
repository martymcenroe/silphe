"""The session file is not created until something is recorded — issue #78.

The game builds a Recorder for the default player before it asks who is
playing, and another for whoever is chosen. Opening the file eagerly meant
every launch where a name was picked left an empty session file behind in the
default player's directory, forever.
"""

import json
import os

import pytest

from silphe.core import Recorder


@pytest.fixture(autouse=True)
def recordings(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path / "recordings"))
    return tmp_path / "recordings"


def files_in(d):
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def test_a_new_recorder_creates_no_file(recordings):
    rec = Recorder(device="mouse", player=None)
    assert rec.path, "the path is still settled up front"
    assert not os.path.exists(rec.path)
    assert files_in(recordings) == []
    rec.close()


def test_the_directory_is_still_made_so_the_player_menu_lists_them(recordings):
    """known_players() scans for `recordings-<name>` dirs. Deferring the file
    must not defer the directory, or a player would vanish from the launch menu
    until they had recorded a round."""
    from silphe.core import known_players

    rec = Recorder(device="mouse", player="Rebecca")
    assert os.path.isdir(str(recordings) + "-Rebecca")
    assert "Rebecca" in known_players()
    rec.close()


def test_the_first_write_creates_it(recordings):
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    assert os.path.exists(rec.path)
    assert files_in(recordings) == [os.path.basename(rec.path)]
    rec.close()


def test_a_session_that_records_nothing_leaves_nothing(recordings):
    """The launch case: a recorder built, then closed unused when the player is
    chosen."""
    rec = Recorder(device="mouse", player=None)
    rec.close()
    assert files_in(recordings) == []


def test_switching_player_at_launch_leaves_no_empty_file(recordings):
    """What #78 was actually about, end to end at the Recorder level."""
    default = Recorder(device="mouse", player=None)
    default.close()                                        # nothing was played yet
    chosen = Recorder(device="mouse", player="Rebecca")
    chosen.write({"kind": "acquire"})
    chosen.close()

    assert files_in(recordings) == [], "an empty default session was left behind"
    assert files_in(str(recordings) + "-Rebecca") == [os.path.basename(chosen.path)]


def test_reopening_an_unused_recorder_still_creates_nothing(recordings):
    rec = Recorder(device="mouse", player=None)
    rec.open_session()
    assert not os.path.exists(rec.path)
    assert files_in(recordings) == []
    rec.close()


def test_reopening_after_writing_keeps_what_was_written(recordings):
    """The session filename carries a whole-second timestamp, so a reopen
    inside the same second names the same file and appends to it. That is
    pre-existing and not what this asserts: what matters is that reopening
    never loses a record.
    """
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    first = rec.path
    rec.open_session()
    rec.write({"kind": "acquire"})
    rec.close()

    kinds = []
    for name in files_in(recordings):
        with open(os.path.join(recordings, name), encoding="utf-8") as f:
            kinds += [json.loads(x)["kind"] for x in f if x.strip()]
    assert sorted(kinds) == ["acquire", "hold"]
    assert os.path.exists(first)


def test_writing_after_close_still_fails_loudly(recordings):
    """Deferring the open must not turn a finished session into one that
    quietly reopens on the next write."""
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    rec.close()
    with pytest.raises(ValueError):
        rec.write({"kind": "acquire"})


def test_writing_after_close_does_not_create_the_file_either(recordings):
    rec = Recorder(device="mouse", player=None)
    rec.close()
    with pytest.raises(ValueError):
        rec.write({"kind": "hold"})
    assert files_in(recordings) == []


def test_closing_twice_is_harmless(recordings):
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    rec.close()
    rec.close()
