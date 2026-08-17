from __future__ import annotations

import json
import time

from endfield_pcap import diagnostic
from endfield_pcap.diagnostic import _list_npcap_devices_with_timeout, _summarize_session_log


def test_summarize_session_log_counts_loadout_and_scene(tmp_path) -> None:
    log_path = tmp_path / "session_test.ndjson"
    rows = [
        {"type": "LOADOUT", "timestamp_ms": 1_700_000_000_000, "rows": [{"slot": 0}, {"slot": 1}]},
        {"type": "SC_SELF_SCENE_INFO", "timestamp_ms": 1_700_000_001_000, "char_list": [{"id": 1}]},
        {"type": "BattleOpTriggerAction", "timestamp_ms": 1_700_000_002_000},
    ]
    log_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    summary = _summarize_session_log(log_path)

    assert summary.lines == 3
    assert summary.json_errors == 0
    assert summary.loadout_rows == 2
    assert summary.scene_chars == 1
    assert summary.type_counts["BattleOpTriggerAction"] == 1
    assert summary.first_ts_ms == 1_700_000_000_000
    assert summary.last_ts_ms == 1_700_000_002_000


def test_list_npcap_devices_reports_timeout(monkeypatch) -> None:
    class SlowWpcap:
        def list_devices(self):
            time.sleep(0.1)
            return []

    monkeypatch.setattr(diagnostic, "Wpcap", SlowWpcap)

    devices, error = _list_npcap_devices_with_timeout(timeout_sec=0.01)

    assert devices is None
    assert error is not None
    assert "TimeoutError" in error


def test_list_npcap_devices_reports_driver_error(monkeypatch) -> None:
    class FailingWpcap:
        def list_devices(self):
            raise RuntimeError("driver stuck")

    monkeypatch.setattr(diagnostic, "Wpcap", FailingWpcap)

    devices, error = _list_npcap_devices_with_timeout(timeout_sec=1)

    assert devices is None
    assert error == "RuntimeError: driver stuck"


def test_status_summary_exposes_protocol_decode_failures(tmp_path) -> None:
    before = diagnostic.Snapshot(
        path=tmp_path / "status.json",
        exists=True,
        payload={"metrics": {"decompression_errors": 1, "protobuf_decode_errors": 2}},
        error=None,
        size=1,
        mtime=None,
    )
    after = diagnostic.Snapshot(
        path=tmp_path / "status.json",
        exists=True,
        payload={
            "metrics": {"decompression_errors": 3, "protobuf_decode_errors": 5},
            "reliability_flags": ["session_body_decompression_failed", "protobuf_decode_failed"],
        },
        error=None,
        size=1,
        mtime=None,
    )

    lines: list[str] = []
    diagnostic._add_status_lines(lines, "sample", after)
    delta = diagnostic._append_delta(lines, before, after)

    rendered = "\n".join(lines)
    assert "decompression_errors=3" in rendered
    assert "protobuf_decode_errors=5" in rendered
    assert "reliability_flags=session_body_decompression_failed,protobuf_decode_failed" in rendered
    assert delta["decompression_errors"] == 2
    assert delta["protobuf_decode_errors"] == 3
