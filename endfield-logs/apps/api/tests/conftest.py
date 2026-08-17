from __future__ import annotations

from pathlib import Path

import pytest


DATA_SENTINEL = Path(__file__).resolve().parents[3] / "data" / "akedata" / "character" / "manifest.json"

HEALTH_TESTS_REQUIRING_GAME_DATA = {
    "test_crisis_fragment_aliases_filter_by_official_stage_slug_only",
    "test_war_echo_highest_stages_have_separate_rankings_and_lower_difficulty_is_excluded",
    "test_contract_tags_are_exposed_on_public_records",
    "test_local_game_catalog_endpoints",
    "test_local_game_semantic_endpoints",
    "test_local_game_semantic_hint_endpoints",
    "test_uploader_battle_upload_endpoints",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if DATA_SENTINEL.is_file():
        return
    reason = "generated game-data resources are not distributed in the public repository"
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if item.path.name == "test_public_data_assets.py" or item.name in HEALTH_TESTS_REQUIRING_GAME_DATA:
            item.add_marker(marker)

