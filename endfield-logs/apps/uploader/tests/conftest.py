from __future__ import annotations

from pathlib import Path

import pytest


DATA_SENTINEL = Path(__file__).resolve().parents[3] / "data" / "local_tables" / "NumIdStrTable.json"

TESTS_REQUIRING_GAME_DATA = {
    "test_build_battle_upload_payload_corrects_source_skill_refine_hint",
    "test_build_battle_upload_payload_from_embedded_log",
    "test_build_battle_upload_payloads_split_close_retries_by_official_timer_and_keeps_dungeon_context",
    "test_build_battle_upload_payloads_uses_official_timer_game_id_without_dungeon_context",
    "test_build_battle_upload_payload_maps_admin_canonical_loadout_to_endmin_variant",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if DATA_SENTINEL.is_file():
        return
    marker = pytest.mark.skip(
        reason="generated game-data resources are not distributed in the public repository"
    )
    for item in items:
        if item.name in TESTS_REQUIRING_GAME_DATA:
            item.add_marker(marker)

