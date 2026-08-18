from __future__ import annotations

import json
import os

import overlay


def test_live_overlay_status_displays_official_dungeon_instead_of_boss() -> None:
    class TailerStub:
        @staticmethod
        def _live_core_rows():
            return (
                {},
                {},
                {
                    "battle": {
                        "dungeon_name": "斧柄纪年·残酷",
                        "boss_name": "精锐行刑人",
                        "boss_key": "eny_0000_example",
                        "duration_ms": 12_345,
                        "rdps_available": True,
                    }
                },
            )

    status = overlay.LogTailer.get_status_snapshot(TailerStub())

    assert status == {"dungeonName": "斧柄纪年·残酷", "elapsed": 12.345}
    assert "精锐行刑人" not in status.values()


def test_live_overlay_exposes_official_stage_before_first_hit() -> None:
    parser = overlay.LiveOverlayBattleParser()
    parser.feed_line(
        "[10:00:00.000] DUNGEON_CONTEXT "
        "dungeonId=indie_battletower004_ex source=SC_SELF_SCENE_INFO"
    )

    snapshot = parser.snapshot()

    assert snapshot is not None
    assert snapshot["battle"]["dungeon_name"] == "斧柄纪年·残酷"
    assert snapshot["participants"] == []


def test_stale_fatal_service_status_remains_visible(monkeypatch, tmp_path) -> None:
    status_file = tmp_path / "trace.log.status.json"
    payload = {
        "state": "live",
        "fatal_error": {
            "task": "packet-loop",
            "type": "AttributeError",
            "message": "FieldDescriptor.label is unavailable",
        },
    }
    status_file.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(status_file, (100.0, 100.0))
    monkeypatch.setattr(overlay, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(overlay.time, "time", lambda: 200.0)

    status = overlay.read_service_status()

    assert status == payload
    assert overlay.service_status_text(status, "zh") == "状态：采集异常（AttributeError）"
    assert overlay.service_metrics_text(status, "zh") == "错误：FieldDescriptor.label is unavailable"
    assert overlay.service_status_text(status, "en") == "Status: Capture Error（AttributeError）"
    assert overlay.service_metrics_text(status, "en") == "Error: FieldDescriptor.label is unavailable"


def test_stale_healthy_service_status_is_disconnected(monkeypatch, tmp_path) -> None:
    status_file = tmp_path / "trace.log.status.json"
    status_file.write_text(json.dumps({"state": "live"}), encoding="utf-8")
    os.utime(status_file, (100.0, 100.0))
    monkeypatch.setattr(overlay, "STATUS_FILE", str(status_file))
    monkeypatch.setattr(overlay.time, "time", lambda: 200.0)

    assert overlay.read_service_status() is None
