"""Capture-kernel tests (silphe.core) — issues #48 (extraction) and #49
(schema freeze + contract)."""

import json

from silphe.core import KERNEL_FIELDS, SCHEMA_VERSION, Recorder


def test_recorder_stamps_kernel_fields_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path))
    rec = Recorder(device="Trackpad", player="Rebecca")
    rec.write({"kind": "hold", "samples": [[0.0, 1, 2]]})
    rec.write({"kind": "acquire", "click": {"err": 3}})
    rec.close()

    # session file lands in the player's sibling dir, device lower-cased
    assert rec.path.startswith(str(tmp_path) + "-Rebecca")
    assert rec.path.endswith("-trackpad.jsonl")

    lines = [json.loads(x) for x in open(rec.path, encoding="utf-8") if x.strip()]
    assert len(lines) == 2
    for rowa in lines:
        assert rowa["schema_version"] == SCHEMA_VERSION
        assert rowa["device"] == "trackpad"
        assert rowa["player"] == "Rebecca"
        assert isinstance(rowa["os"], str) and rowa["os"]
    # the game's own fields survive alongside the kernel's
    assert lines[0]["kind"] == "hold"
    assert lines[1]["click"] == {"err": 3}


def test_recorder_default_player_writes_to_base_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path))
    rec = Recorder()  # default device, no player
    rec.write({"kind": "track"})
    rec.close()
    row = json.loads(open(rec.path, encoding="utf-8").readline())
    assert rec.path.startswith(str(tmp_path) + "/session-") or \
           rec.path.startswith(str(tmp_path) + "\\session-")
    assert row["device"] == "mouse"
    assert row["player"] == ""


def test_schema_contract_is_frozen(tmp_path, monkeypatch):
    """If the kernel's stamped fields drift, this fails — forcing a conscious
    SCHEMA_VERSION decision rather than a silent breaking change (#49)."""
    assert KERNEL_FIELDS == ("schema_version", "device", "os", "player")
    assert isinstance(SCHEMA_VERSION, int) and SCHEMA_VERSION >= 1

    monkeypatch.setenv("SILPHE_RECORDINGS", str(tmp_path))
    rec = Recorder(device="mouse", player=None)
    rec.write({"kind": "hold"})
    rec.close()
    row = json.loads(open(rec.path, encoding="utf-8").readline())
    for field in KERNEL_FIELDS:
        assert field in row, f"kernel must stamp {field!r} on every record"
