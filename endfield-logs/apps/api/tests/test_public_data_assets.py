from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.schemas.public import BattleParticipantResponse, BattleRosterEntryResponse, RoleSkillStatResponse, TimelineEventResponse
from app.schemas.uploader import UploadTimelineEventRequest
from app.services.public_data import BOSS_SEEDS, BossSeed, DemoBattle, DemoPublicDataService
from app.services.public_data import _enrich_timeline_event_damage_identity, _normalize_public_asset_url, _weapon_icon_url
from app.services.public_data import _normalize_skill_display_name
from app.services.public_data import (
    ADMIN_STATISTICS_CHARACTER_KEY,
    RANKING_DAMAGE_GATE_MIN_SAMPLES,
    SIX_STAR_STATISTICS_CATALOG,
    _build_poise_damage_response,
    _enrich_participant_character_identity,
    _enrich_roster_entry_character_identity,
    _normalize_role_skill_stat_character_identity,
    _normalize_timeline_event_character_identity,
)


def _make_test_battle(
    battle_id: str,
    *,
    uploader_user_id: str = "user-a",
    boss_slug: str = "boss-test",
    boss_key: str = "boss-test",
    boss_name: str = "测试首领",
    dungeon_name: str = "测试副本",
    duration_ms: int,
    total_dps: float,
    total_damage: int | None = None,
    contract_tag_score: int | None = None,
    official_timer_end_seen: bool = True,
    parser_version: str = "raw-log-parser-v34",
    character_potential: int | None = 0,
    rdps_strict_ok: bool = True,
) -> DemoBattle:
    started_at = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    participant = BattleParticipantResponse(
        characterKey="chr_0027_tangtang",
        characterName="糖糖",
        characterProfession="突击",
        characterAvatarUrl=None,
        accountDisplayName=uploader_user_id,
        totalDamage=total_damage or int(total_dps * duration_ms / 1000),
        dps=total_dps,
        rdps=total_dps,
        maxHit=None,
        critRate=None,
    )
    return DemoBattle(
        battle_id=battle_id,
        uploader_user_id=uploader_user_id,
        uploader_nickname=uploader_user_id,
        boss_key=boss_key,
        boss_slug=boss_slug,
        boss_name=boss_name,
        dungeon_name=dungeon_name,
        duration_ms=duration_ms,
        battle_start_at=started_at,
        battle_end_at=started_at + timedelta(milliseconds=duration_ms),
        total_damage=participant.totalDamage,
        total_dps=total_dps,
        roster=[
            BattleRosterEntryResponse(
                slot=1,
                characterKey="chr_0027_tangtang",
                characterName="糖糖",
                characterProfession="突击",
                characterAvatarUrl=None,
                accountDisplayName=uploader_user_id,
                characterPotential=character_potential,
            )
        ],
        participants=[participant],
        timeline_events=[],
        role_skill_stats=[],
        parser_version=parser_version,
        rules_version="test",
        battle_fingerprint=battle_id,
        contract_tag_score=contract_tag_score,
        official_timer_end_seen=official_timer_end_seen,
        time_source="game_timer",
        timer_window_valid=True,
        rdps_preflight_ok=True,
        rdps_strict_ok=rdps_strict_ok,
        rdps_preflight_blocker_count=0,
    )


def _make_damage_event(target_key: str, value: int) -> TimelineEventResponse:
    return TimelineEventResponse(
        tsMsFromStart=1000,
        laneType="skill",
        sourceCharacterKey="chr_0027_tangtang",
        sourceCharacterName="糖糖",
        targetCharacterKey=target_key,
        targetCharacterName=target_key,
        eventKey="chr_0027_tangtang_attack1",
        eventName="A1",
        value=value,
        important=True,
    )


def _make_statistics_participant(
    character_key: str,
    character_name: str,
    value: float,
    *,
    rdps: float | None = None,
) -> BattleParticipantResponse:
    return BattleParticipantResponse(
        characterKey=character_key,
        characterName=character_name,
        characterProfession=None,
        characterAvatarUrl=None,
        accountDisplayName="statistics-user",
        totalDamage=max(0, int(value * 60)),
        dps=value,
        rdps=value if rdps is None else rdps,
        maxHit=None,
        critRate=None,
    )


def _make_statistics_service(battles: list[DemoBattle]) -> DemoPublicDataService:
    for battle in battles:
        existing_by_key = {entry.characterKey: entry for entry in battle.roster if entry.characterKey}
        fallback_potential = battle.roster[0].characterPotential if len(battle.roster) == 1 else 0
        battle.roster = [
            BattleRosterEntryResponse(
                slot=index + 1,
                characterKey=participant.characterKey,
                characterName=participant.characterName,
                characterProfession=participant.characterProfession,
                characterAvatarUrl=participant.characterAvatarUrl,
                accountDisplayName=participant.accountDisplayName,
                characterPotential=(
                    existing_by_key[participant.characterKey].characterPotential
                    if participant.characterKey in existing_by_key
                    else fallback_potential
                ),
            )
            for index, participant in enumerate(battle.participants)
        ]
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {
        "boss-test": BossSeed(
            key="boss-test",
            slug="boss-test",
            name="测试首领",
            dungeon_name="测试副本",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        ),
        "indie_group_ccdg": BossSeed(
            key="eny_0090_wgabyss",
            slug="indie_group_ccdg",
            name="破潮之像",
            dungeon_name="危机合约",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        ),
    }
    service._list_uploaded_battle_summaries = lambda boss_slug=None: [
        battle for battle in battles if boss_slug is None or battle.boss_slug == boss_slug
    ]
    return service


def test_contingency_contract_boss_seed_is_available() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {boss.slug: boss for boss in BOSS_SEEDS}

    assert service._resolve_boss_slug("indie_group_ccdg", "eny_0090_wgabyss", "破潮之像") == "indie_group_ccdg"
    boss = service.bosses_by_slug["indie_group_ccdg"]
    assert boss.key == "eny_0090_wgabyss"
    assert boss.name == "破潮之像"
    assert boss.dungeon_name == "危机合约"


def test_boss_identity_never_changes_stage_routing() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {boss.slug: boss for boss in BOSS_SEEDS}

    assert (
        service._resolve_boss_slug(
            "indie_battletower004_ex",
            "eny_0082_hsbear",
            "死兽鸣吼",
        )
        == "indie_battletower004_ex"
    )
    assert (
        service._resolve_boss_slug(
            "unknown_dungeon",
            "eny_0051_rodin",
            "“碾骨之拳”罗丹",
        )
        == "unknown-dungeon"
    )
    assert (
        service._canonical_uploaded_boss_slug(
            "unknown_dungeon",
            "eny_0051_rodin",
        )
        == "unknown_dungeon"
    )


def test_20260717_ranking_seeds_are_open() -> None:
    slugs = {boss.slug for boss in BOSS_SEEDS}
    assert {
        "dung02_group_bossrush03",
        "dung02_group_minibossrush02",
        "indie_hard022_s",
        "indie_hard023_s",
        "indie_hard024_s",
        "indie_hard025_s",
        "indie_battletower001_ex",
        "indie_battletower002_ex",
        "indie_battletower003_ex",
        "indie_battletower004_ex",
        "indie_battletower005_ex",
        "indie_battletower006_ex",
        "indie_battletower007_ex",
        "indie_battletower008_ex",
    }.issubset(slugs)


def test_all_war_echo_highest_stages_have_separate_ranking_seeds() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {boss.slug: boss for boss in BOSS_SEEDS}

    for index in range(1, 9):
        slug = f"indie_battletower{index:03d}_ex"
        assert service._resolve_boss_slug(slug, "", "") == slug
    assert service._resolve_boss_slug("indie_battletower006_s", "", "") == "indie_battletower006_s"
    assert service._canonical_uploaded_boss_slug("indie_group_twdg", "eny_0082_hsbear") == "indie_group_twdg"
    boss = service.bosses_by_slug["indie_battletower004_ex"]
    assert boss.name == "斧柄纪年·残酷"
    assert boss.dungeon_name == "战争回响"
    assert service._display_boss_name(
        boss_slug="indie_battletower007_ex",
        boss_key="eny_0082_hsbear",
        boss_name="天鼓",
        dungeon_name="战争回响",
    ) == "死兽鸣吼·残酷"


def test_normalize_public_asset_url_maps_akedata_public_path_to_local_images() -> None:
    assert _normalize_public_asset_url("/public/images/character/charremoteicon/icon_chr_0027_tangtang.png") == "/images/character/charremoteicon/icon_chr_0027_tangtang.png"


def test_normalize_public_asset_url_maps_akedata_hosted_image_to_local_images() -> None:
    assert (
        _normalize_public_asset_url("https://www.akedata.top/public/images/character/charremoteicon/icon_chr_0027_tangtang.png")
        == "/images/character/charremoteicon/icon_chr_0027_tangtang.png"
    )


def test_normalize_public_asset_url_omits_missing_or_empty_path() -> None:
    assert _normalize_public_asset_url(None) is None
    assert _normalize_public_asset_url("") is None
    assert _normalize_public_asset_url("   ") is None


def test_normalize_public_asset_url_normalizes_akedata_hosted_image() -> None:
    assert (
        _normalize_public_asset_url("https://www.akedata.top/public/images/equip/iconbig/item_equip_not_synced.png")
        == "/images/equip/iconbig/item_equip_not_synced.png"
    )


def test_normalize_public_asset_url_normalizes_local_images_path() -> None:
    assert (
        _normalize_public_asset_url("/images/equip/iconbig/item_equip_not_synced.png")
        == "/images/equip/iconbig/item_equip_not_synced.png"
    )


def test_normalize_public_asset_url_preserves_non_akedata_urls() -> None:
    assert _normalize_public_asset_url("https://cdn.example.com/demo.png") == "https://cdn.example.com/demo.png"


def test_weapon_icon_url_falls_back_to_local_weapon_template_icon() -> None:
    assert _weapon_icon_url(None, "wpn_lance_0015") == "/images/weapon/icon/wpn_lance_0015.png"
    assert _weapon_icon_url("/public/images/weapon/icon/wpn_lance_0015.png", "wpn_lance_0015") == "/images/weapon/icon/wpn_lance_0015.png"


def test_build_poise_damage_response_accepts_upload_model() -> None:
    poise_damage = UploadTimelineEventRequest.PoiseDamage(
        type="PoiseDamage",
        value=-18,
        current_value=262,
        source="chr_0028_wulfa_attack5",
        source_int=123,
        orig_source="chr_0028_wulfa_attack5",
        orig_source_int=1997,
    )

    response = _build_poise_damage_response(poise_damage)

    assert response is not None
    assert response.value == -18
    assert response.source == "chr_0028_wulfa_attack5"
    assert response.orig_source_int == 1997


def test_public_data_normalizes_physical_crush_trigger_damage() -> None:
    event = TimelineEventResponse(
        tsMsFromStart=10226,
        laneType="skill",
        sourceCharacterKey="chr_0003_endminf",
        sourceCharacterName="管理员",
        targetCharacterKey="eny_0051_rodin",
        targetCharacterName="“碾骨之拳”罗丹",
        eventKey="buff_common_cryst_triggered_physical_break",
        eventName="碎冰",
        value=41592,
        damageElement="cryst",
        important=True,
    )

    enriched = _enrich_timeline_event_damage_identity(event)

    assert enriched.eventName == "猛击"
    assert enriched.damageElement == "physical"
    assert enriched.damageSchool == "physical"
    assert _normalize_skill_display_name("碎冰", "buff_common_cryst_triggered_physical_break") == "猛击"


def test_public_data_normalizes_raw_mifu_character_identity() -> None:
    participant = _enrich_participant_character_identity(
        BattleParticipantResponse(
            characterKey="chr_0031_mifu",
            characterName="chr_0031_mifu",
            characterProfession=None,
            characterAvatarUrl=None,
            accountDisplayName="tester",
            totalDamage=100,
            dps=100,
            rdps=100,
            maxHit=None,
            critRate=None,
        )
    )
    roster_entry = _enrich_roster_entry_character_identity(
        BattleRosterEntryResponse(
            slot=1,
            characterKey="chr_0031_mifu",
            characterName="chr_0031_mifu",
            characterProfession=None,
            characterAvatarUrl=None,
            accountDisplayName="tester",
        )
    )
    event = _normalize_timeline_event_character_identity(
        TimelineEventResponse(
            tsMsFromStart=1000,
            laneType="skill",
            sourceCharacterKey="chr_0031_mifu",
            sourceCharacterName="chr_0031_mifu",
            targetCharacterKey="chr_0031_mifu",
            targetCharacterName="chr_0031_mifu",
            targetPlayerKey="chr_0031_mifu",
            eventKey="chr_0031_mifu_attack1",
            eventName="A1",
            value=100,
            rdpsContributions=[
                TimelineEventResponse.RdpsContributionResponse(
                    characterKey="chr_0031_mifu",
                    characterName="chr_0031_mifu",
                    value=100,
                )
            ],
            important=True,
        )
    )
    stat = _normalize_role_skill_stat_character_identity(
        RoleSkillStatResponse(
            characterName="chr_0031_mifu",
            skillKey="chr_0031_mifu_attack1",
            skillName="A1",
            castCount=1,
            totalDamage=100,
            avgDamage=100,
            maxDamage=100,
        )
    )

    assert participant.characterName == "弭弗"
    assert participant.characterProfession == "近卫"
    assert participant.characterAvatarUrl == "/images/character/charremoteicon/icon_chr_0031_mifu.png"
    assert roster_entry.characterName == "弭弗"
    assert event.sourceCharacterName == "弭弗"
    assert event.targetCharacterName == "弭弗"
    assert event.rdpsContributions[0].characterName == "弭弗"
    assert stat.characterName == "弭弗"


def test_public_data_normalizes_raw_camille_character_identity() -> None:
    participant = _enrich_participant_character_identity(
        BattleParticipantResponse(
            characterKey="chr_0033_camille",
            characterName="chr_0033_camille",
            characterProfession="未归类",
            characterAvatarUrl=None,
            accountDisplayName="tester",
            totalDamage=100,
            dps=100,
            rdps=100,
            maxHit=None,
            critRate=None,
        )
    )
    roster_entry = _enrich_roster_entry_character_identity(
        BattleRosterEntryResponse(
            slot=1,
            characterKey="chr_0033_camille",
            characterName="chr_0033_camille",
            characterProfession="未归类",
            characterAvatarUrl=None,
            accountDisplayName="tester",
        )
    )

    assert participant.characterName == "卡缪"
    assert participant.characterProfession == "先锋"
    assert participant.characterAvatarUrl == "/images/character/charremoteicon/icon_chr_0033_camille.png"
    assert participant.characterElement == "fire"
    assert roster_entry.characterName == "卡缪"
    assert roster_entry.characterAvatarUrl == "/images/character/charremoteicon/icon_chr_0033_camille.png"


def test_clear_flag_requires_completion_signal_when_timer_fields_are_present() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)

    assert (
        service._validate_upload_clear_flag(
            requested_clear_flag=True,
            boss_slug="indie_hard001_s",
            total_damage=827303,
            timeline_events=[],
            timer_end_seen=False,
            official_timer_end_seen=False,
        )
        is False
    )
    assert (
        service._validate_upload_clear_flag(
            requested_clear_flag=True,
            boss_slug="indie_hard001_s",
            total_damage=827303,
            timeline_events=[],
            timer_end_seen=True,
            official_timer_end_seen=False,
        )
        is True
    )
    assert (
        service._validate_upload_clear_flag(
            requested_clear_flag=True,
            boss_slug="indie_hard001_s",
            total_damage=827303,
            timeline_events=[],
        )
        is False
    )


def test_war_echo_clear_flag_requires_official_timer_end() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)

    assert (
        service._validate_upload_clear_flag(
            requested_clear_flag=True,
            dungeon_key="indie_battletower007_ex",
            boss_slug="indie_battletower007_ex",
            total_damage=2_500_000,
            timeline_events=[],
            timer_end_seen=True,
            official_timer_end_seen=False,
        )
        is False
    )
    assert (
        service._validate_upload_clear_flag(
            requested_clear_flag=True,
            dungeon_key="indie_battletower007_ex",
            boss_slug="indie_battletower007_ex",
            total_damage=2_500_000,
            timeline_events=[],
            timer_end_seen=True,
            official_timer_end_seen=True,
            time_source="game_timer",
            timer_window_valid=True,
        )
        is True
    )


def test_public_ranked_battles_keep_fastest_valid_clear_per_account() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    slow_high_dps = _make_test_battle("slow-high-dps", duration_ms=70_000, total_dps=200_000)
    fast_low_dps = _make_test_battle("fast-low-dps", duration_ms=60_000, total_dps=150_000)
    service._list_uploaded_battles = lambda boss_slug=None: [slow_high_dps, fast_low_dps]

    ranked = service._list_public_ranked_battles("boss-test")

    assert [battle.battle_id for battle in ranked] == ["fast-low-dps"]


def test_public_ranked_battles_exclude_undamaged_fake_clear_on_fixed_hp_boss() -> None:
    # 固定血量 boss：正常通关伤害紧密聚集在血量附近；boss rush 只杀部分/异常结算会以
    # 极低伤害“通关”（clear_flag + official_timer 皆误真）。伤害不足中位数 60% 的记录剔除。
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    normal_clears = [
        _make_test_battle(
            f"normal-{i}",
            uploader_user_id=f"user-{i}",
            duration_ms=15_000 + i * 100,
            total_dps=150_000,
            total_damage=2_290_000,
        )
        for i in range(RANKING_DAMAGE_GATE_MIN_SAMPLES)
    ]
    fake_clear = _make_test_battle(
        "fake-8s",
        uploader_user_id="user-fake",
        duration_ms=8_000,  # 虚短
        total_dps=19_000,
        total_damage=157_000,  # boss 血量 ~6.9%，没真打死
    )
    service._list_uploaded_battles = lambda boss_slug=None: [*normal_clears, fake_clear]

    ranked = service._list_public_ranked_battles("boss-test")
    ranked_ids = {battle.battle_id for battle in ranked}

    assert "fake-8s" not in ranked_ids  # 假通关被剔除，即使时长最短
    assert "normal-0" in ranked_ids


def test_public_ranked_battles_keep_low_damage_clear_without_enough_samples() -> None:
    # 样本不足（< 阈值）时不套用伤害闸，避免小样本 boss 误伤正常低伤记录。
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    normal_clears = [
        _make_test_battle(
            f"few-{i}",
            uploader_user_id=f"user-{i}",
            duration_ms=15_000 + i * 100,
            total_dps=150_000,
            total_damage=2_290_000,
        )
        for i in range(3)
    ]
    low_damage = _make_test_battle(
        "low-but-kept",
        uploader_user_id="user-low",
        duration_ms=8_000,
        total_dps=19_000,
        total_damage=157_000,
    )
    service._list_uploaded_battles = lambda boss_slug=None: [*normal_clears, low_damage]

    ranked = service._list_public_ranked_battles("boss-test")
    ranked_ids = {battle.battle_id for battle in ranked}

    assert "low-but-kept" in ranked_ids  # 样本不足，伤害闸不生效


def test_crisis_contract_public_ranked_battles_keep_highest_score_per_account() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    low_score_fast = _make_test_battle(
        "low-score-fast",
        boss_slug="indie_group_ccdg",
        boss_key="eny_0090_wgabyss",
        boss_name="破潮之像",
        dungeon_name="危机合约",
        duration_ms=50_000,
        total_dps=200_000,
        contract_tag_score=6,
    )
    high_score_slow = _make_test_battle(
        "high-score-slow",
        boss_slug="indie_group_ccdg",
        boss_key="eny_0090_wgabyss",
        boss_name="破潮之像",
        dungeon_name="危机合约",
        duration_ms=70_000,
        total_dps=150_000,
        contract_tag_score=10,
    )
    service._list_uploaded_battles = lambda boss_slug=None: [low_score_fast, high_score_slow]

    ranked = service._list_public_ranked_battles("indie_group_ccdg")

    assert [battle.battle_id for battle in ranked] == ["high-score-slow"]


def test_nephis_upload_clear_validation_rejects_single_phase_damage() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)

    assert service._validate_upload_clear_flag(
        requested_clear_flag=True,
        boss_slug="dung02_group_bossrush02",
        total_damage=1_559_179,
        timeline_events=[_make_damage_event("eny_0078_nefarp1", 1_559_179)],
    ) is False
    assert service._validate_upload_clear_flag(
        requested_clear_flag=True,
        boss_slug="dung02_group_bossrush02",
        total_damage=1_742_621,
        timeline_events=[_make_damage_event("eny_0079_nefarp2", 1_742_621)],
    ) is False


def test_nephis_upload_clear_validation_accepts_two_phase_or_full_unknown_damage() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)

    assert service._validate_upload_clear_flag(
        requested_clear_flag=True,
        boss_slug="dung02_group_bossrush02",
        total_damage=3_301_789,
        timeline_events=[
            _make_damage_event("eny_0078_nefarp1", 1_559_178),
            _make_damage_event("eny_0079_nefarp2", 1_742_611),
        ],
        timer_end_seen=True,
    ) is True
    assert service._validate_upload_clear_flag(
        requested_clear_flag=True,
        boss_slug="dung02_group_bossrush02",
        total_damage=3_301_787,
        timeline_events=[_make_damage_event("eny_0000_unknown", 3_301_787)],
        timer_end_seen=True,
    ) is True


def test_boss_rankings_sort_by_kill_time_before_metric_value() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {
        "boss-test": BossSeed(
            key="boss-test",
            slug="boss-test",
            name="测试首领",
            dungeon_name="测试副本",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        )
    }
    battles = [
        _make_test_battle("slow-high-dps", uploader_user_id="user-a", duration_ms=70_000, total_dps=200_000),
        _make_test_battle("fast-low-dps", uploader_user_id="user-b", duration_ms=60_000, total_dps=150_000),
        _make_test_battle("middle-dps", uploader_user_id="user-c", duration_ms=65_000, total_dps=175_000),
    ]
    service._iter_boss_battles = lambda boss_slug, metric="dps": battles

    ranking = service.get_boss_rankings("boss-test", "dps")

    assert [row.battleId for row in ranking.rows] == ["fast-low-dps", "middle-dps", "slow-high-dps"]
    assert [row.rank for row in ranking.rows] == [1, 2, 3]
    assert ranking.rows[0].accountId == "user-b"
    assert ranking.rows[0].scorePercent == 100
    assert ranking.rows[1].scorePercent == 67


def test_rdps_rankings_require_per_battle_strict_audit() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    strict = _make_test_battle(
        "strict-rdps",
        uploader_user_id="strict-user",
        duration_ms=60_000,
        total_dps=100_000,
        rdps_strict_ok=True,
    )
    blocked = _make_test_battle(
        "blocked-rdps",
        uploader_user_id="blocked-user",
        duration_ms=50_000,
        total_dps=200_000,
        rdps_strict_ok=False,
    )
    service._list_uploaded_battles = lambda boss_slug=None: [strict, blocked]

    assert [battle.battle_id for battle in service._list_public_ranked_battles("boss-test", metric="dps")] == [
        "blocked-rdps",
        "strict-rdps",
    ]
    assert [battle.battle_id for battle in service._list_public_ranked_battles("boss-test", metric="rdps")] == [
        "strict-rdps"
    ]


def test_character_statistics_catalog_has_fifteen_six_star_characters_and_one_admin() -> None:
    assert len(SIX_STAR_STATISTICS_CATALOG) == 16
    admin_rows = [entry for entry in SIX_STAR_STATISTICS_CATALOG if entry.name == "管理员"]
    assert len(admin_rows) == 1
    assert admin_rows[0].char_id == ADMIN_STATISTICS_CHARACTER_KEY


def test_character_statistics_keep_all_runs_and_sort_sufficient_samples_first() -> None:
    battles: list[DemoBattle] = []
    for index, value in enumerate((10.0, 20.0, 30.0, 40.0, 50.0)):
        battle = _make_test_battle(
            f"tangtang-{index}",
            uploader_user_id="same-user",
            duration_ms=60_000,
            total_dps=value,
        )
        battle.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", value)]
        battles.append(battle)
    for index, value in enumerate((100.0, 110.0, 120.0, 130.0)):
        battle = _make_test_battle(
            f"mifu-{index}",
            uploader_user_id="same-user",
            duration_ms=60_000,
            total_dps=value,
        )
        battle.participants = [_make_statistics_participant("chr_0031_mifu", "弭弗", value)]
        battles.append(battle)
    battles[0].participants.extend(
        [
            _make_statistics_participant("chr_0004_pelica", "佩丽卡", 999.0),
            _make_statistics_participant("chr_0002_endminm", "管理员", 0.0, rdps=0.0),
        ]
    )
    service = _make_statistics_service(battles)

    statistics = service.get_boss_character_statistics("boss-test", "dps", "all")
    rows = {row.characterName: row for row in statistics.rows}

    assert statistics.eligibleBattleCount == 9
    assert statistics.scope == "boss"
    assert statistics.includedBossCount == 1
    assert statistics.totalSampleCount == 9
    assert len(statistics.rows) == len(SIX_STAR_STATISTICS_CATALOG)
    assert rows["汤汤"].sampleCount == 5
    assert rows["汤汤"].rank == 1
    assert rows["汤汤"].p10 == 14.0
    assert rows["汤汤"].p25 == 20.0
    assert rows["汤汤"].median == 30.0
    assert rows["汤汤"].p75 == 40.0
    assert rows["汤汤"].p90 == 46.0
    assert rows["汤汤"].maximum == 50.0
    assert rows["弭弗"].sampleCount == 4
    assert rows["弭弗"].insufficientSamples is True
    assert rows["弭弗"].rank is None
    assert "佩丽卡" not in rows
    assert statistics.rows.index(rows["汤汤"]) < statistics.rows.index(rows["弭弗"])


def test_character_statistics_rdps_excludes_pre_v25_but_dps_keeps_it() -> None:
    old_battle = _make_test_battle(
        "old-parser",
        duration_ms=60_000,
        total_dps=100.0,
        parser_version="raw-log-parser-v24",
    )
    old_battle.participants = [
        _make_statistics_participant("chr_0027_tangtang", "汤汤", 100.0, rdps=200.0)
    ]
    new_battle = _make_test_battle(
        "new-parser",
        duration_ms=60_000,
        total_dps=300.0,
        parser_version="raw-log-parser-v25",
    )
    new_battle.participants = [
        _make_statistics_participant("chr_0027_tangtang", "汤汤", 300.0, rdps=400.0)
    ]
    service = _make_statistics_service([old_battle, new_battle])

    dps = service.get_boss_character_statistics("boss-test", "dps", "all")
    rdps = service.get_boss_character_statistics("boss-test", "rdps", "all")
    dps_row = next(row for row in dps.rows if row.characterName == "汤汤")
    rdps_row = next(row for row in rdps.rows if row.characterName == "汤汤")

    assert dps.eligibleBattleCount == 2
    assert dps_row.sampleCount == 2
    assert dps_row.median == 200.0
    assert rdps.eligibleBattleCount == 1
    assert rdps_row.sampleCount == 1
    assert rdps_row.median == 400.0


def test_character_statistics_render_extreme_values_as_outliers_without_stretching_box() -> None:
    battles: list[DemoBattle] = []
    for character_key, character_name, values in (
        ("chr_0027_tangtang", "汤汤", (10.0, 11.0, 12.0, 13.0, 14.0, 1000.0)),
        ("chr_0031_mifu", "弭弗", (20.0, 21.0, 22.0, 23.0, 24.0, 25.0)),
    ):
        for index, value in enumerate(values):
            battle = _make_test_battle(
                f"outlier-{character_key}-{index}",
                duration_ms=60_000,
                total_dps=value,
            )
            battle.participants = [_make_statistics_participant(character_key, character_name, value)]
            battles.append(battle)

    statistics = _make_statistics_service(battles).get_boss_character_statistics("boss-test", "dps", "all")
    tangtang = next(row for row in statistics.rows if row.characterName == "汤汤")

    assert statistics.totalSampleCount == 12
    assert statistics.totalOutlierCount == 1
    assert tangtang.sampleCount == 6
    assert tangtang.normalSampleCount == 5
    assert tangtang.outlierCount == 1
    assert tangtang.lowerWhisker == 10.0
    assert tangtang.upperWhisker == 14.0
    assert tangtang.median == 12.0
    assert tangtang.maximum == 1000.0
    assert [(point.value, point.count) for point in tangtang.outliers] == [(1000.0, 1)]


def test_character_statistics_time_ranges_and_completion_gate() -> None:
    recent = _make_test_battle("recent", duration_ms=60_000, total_dps=100.0)
    recent.battle_end_at = datetime.now(UTC) - timedelta(days=1)
    recent.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 100.0)]
    old = _make_test_battle("old", duration_ms=60_000, total_dps=200.0)
    old.battle_end_at = datetime.now(UTC) - timedelta(days=8)
    old.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 200.0)]
    incomplete = _make_test_battle(
        "incomplete",
        duration_ms=60_000,
        total_dps=999.0,
        official_timer_end_seen=False,
    )
    incomplete.battle_end_at = datetime.now(UTC) - timedelta(days=1)
    incomplete.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 999.0)]
    service = _make_statistics_service([recent, old, incomplete])

    seven_days = service.get_boss_character_statistics("boss-test", "dps", "7d")
    all_time = service.get_boss_character_statistics("boss-test", "dps", "all")
    seven_day_row = next(row for row in seven_days.rows if row.characterName == "汤汤")
    all_time_row = next(row for row in all_time.rows if row.characterName == "汤汤")

    assert seven_days.eligibleBattleCount == 1
    assert seven_day_row.sampleCount == 1
    assert all_time.eligibleBattleCount == 2
    assert all_time_row.sampleCount == 2


def test_character_statistics_filter_known_character_potential_and_drop_unknown() -> None:
    battles: list[DemoBattle] = []
    for potential, value in ((0, 100.0), (1, 200.0), (5, 300.0), (None, 999.0)):
        battle = _make_test_battle(
            f"potential-{potential}",
            duration_ms=60_000,
            total_dps=value,
            character_potential=potential,
        )
        battle.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", value)]
        battles.append(battle)
    service = _make_statistics_service(battles)

    all_known = service.get_boss_character_statistics("boss-test", "dps", "all", "all")
    zero = service.get_boss_character_statistics("boss-test", "dps", "all", "0")
    one_to_five = service.get_boss_character_statistics("boss-test", "dps", "all", "1-5")
    all_row = next(row for row in all_known.rows if row.characterName == "汤汤")
    zero_row = next(row for row in zero.rows if row.characterName == "汤汤")
    one_to_five_row = next(row for row in one_to_five.rows if row.characterName == "汤汤")

    assert all_known.potential == "all"
    assert all_known.eligibleBattleCount == 3
    assert all_row.sampleCount == 3
    assert all_row.median == 200.0
    assert zero.potential == "0"
    assert zero.eligibleBattleCount == 1
    assert zero_row.sampleCount == 1
    assert zero_row.median == 100.0
    assert one_to_five.potential == "1-5"
    assert one_to_five.eligibleBattleCount == 2
    assert one_to_five_row.sampleCount == 2
    assert one_to_five_row.median == 250.0


def test_character_statistics_are_not_available_for_crisis_contract() -> None:
    service = _make_statistics_service([])

    with pytest.raises(AppError) as error:
        service.get_boss_character_statistics("indie_group_ccdg", "dps", "all")

    assert error.value.status_code == 404
    assert error.value.code == "character_statistics_not_available"


def test_all_character_statistics_combine_bosses_and_exclude_crisis_contract() -> None:
    first = _make_test_battle(
        "first",
        boss_slug="dung01_group_bossrush01",
        boss_key="dung01_group_bossrush01",
        duration_ms=60_000,
        total_dps=100.0,
    )
    first.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 100.0)]
    second = _make_test_battle(
        "second",
        boss_slug="dung01_group_bossrush02",
        boss_key="dung01_group_bossrush02",
        boss_name="另一个首领",
        dungeon_name="另一个副本",
        duration_ms=60_000,
        total_dps=200.0,
    )
    second.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 200.0)]
    crisis = _make_test_battle(
        "crisis",
        boss_slug="indie_group_ccdg",
        boss_key="eny_0090_wgabyss",
        boss_name="破潮之像",
        dungeon_name="危机合约",
        duration_ms=60_000,
        total_dps=999.0,
    )
    crisis.participants = [_make_statistics_participant("chr_0027_tangtang", "汤汤", 999.0)]
    service = _make_statistics_service([first, second, crisis])

    statistics = service.get_all_character_statistics("dps", "all")
    tangtang = next(row for row in statistics.rows if row.characterName == "汤汤")

    assert statistics.scope == "all"
    assert statistics.bossSlug == "all"
    assert statistics.includedBossCount == 2
    assert statistics.eligibleBattleCount == 2
    assert statistics.totalSampleCount == 2
    assert tangtang.sampleCount == 2
    assert tangtang.median == 150.0


def test_crisis_contract_rankings_sort_by_tag_score_before_kill_time() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {
        "indie_group_ccdg": BossSeed(
            key="eny_0090_wgabyss",
            slug="indie_group_ccdg",
            name="破潮之像",
            dungeon_name="危机合约",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        )
    }
    battles = [
        _make_test_battle(
            "low-score-fast",
            uploader_user_id="user-a",
            boss_slug="indie_group_ccdg",
            boss_key="eny_0090_wgabyss",
            boss_name="破潮之像",
            dungeon_name="危机合约",
            duration_ms=50_000,
            total_dps=220_000,
            contract_tag_score=6,
        ),
        _make_test_battle(
            "high-score-slow",
            uploader_user_id="user-b",
            boss_slug="indie_group_ccdg",
            boss_key="eny_0090_wgabyss",
            boss_name="破潮之像",
            dungeon_name="危机合约",
            duration_ms=70_000,
            total_dps=180_000,
            contract_tag_score=10,
        ),
        _make_test_battle(
            "high-score-fast",
            uploader_user_id="user-c",
            boss_slug="indie_group_ccdg",
            boss_key="eny_0090_wgabyss",
            boss_name="破潮之像",
            dungeon_name="危机合约",
            duration_ms=60_000,
            total_dps=160_000,
            contract_tag_score=10,
        ),
    ]
    service._iter_boss_battles = lambda boss_slug, metric="dps": battles

    ranking = service.get_boss_rankings("indie_group_ccdg", "dps")

    assert [row.battleId for row in ranking.rows] == ["high-score-fast", "high-score-slow", "low-score-fast"]
    assert [row.rank for row in ranking.rows] == [1, 2, 3]
    assert [row.scorePercent for row in ranking.rows] == [100, 67, 33]
    assert [row.contractTagScore for row in ranking.rows] == [10, 10, 6]


def test_public_user_rankings_can_be_loaded_by_account_id() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {
        "boss-test": BossSeed(
            key="boss-test",
            slug="boss-test",
            name="测试首领",
            dungeon_name="测试副本",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        )
    }
    battles = [
        _make_test_battle("first", uploader_user_id="user-a", duration_ms=60_000, total_dps=100_000),
        _make_test_battle("second", uploader_user_id="user-b", duration_ms=70_000, total_dps=120_000),
    ]
    service._list_uploaded_battles = lambda boss_slug=None: battles
    service._get_public_user_display_name = lambda account_id: "公开账号"

    response = service.get_public_user_rankings("user-b")

    assert response.accountId == "user-b"
    assert response.accountDisplayName == "公开账号"
    assert response.rankings[0].battleId == "second"
    assert response.rankings[0].rank == 2


def test_boss_rankings_show_team_total_metrics() -> None:
    service = DemoPublicDataService.__new__(DemoPublicDataService)
    service.bosses_by_slug = {
        "boss-test": BossSeed(
            key="boss-test",
            slug="boss-test",
            name="测试首领",
            dungeon_name="测试副本",
            roster=("chr_0027_tangtang", "unknown", "unknown", "unknown"),
            uploader_names=("a", "b", "c"),
            base_duration_ms=60_000,
            base_dps=100_000,
            base_rdps=100_000,
        )
    }
    battle = _make_test_battle("team-total", uploader_user_id="user-a", duration_ms=60_000, total_dps=154_916)
    battle.participants = [
        BattleParticipantResponse(
            characterKey="chr_0027_tangtang",
            characterName="糖糖",
            characterProfession="突击",
            characterAvatarUrl=None,
            accountDisplayName="user-a",
            totalDamage=8_838_480,
            dps=147_308,
            rdps=100_000,
            maxHit=None,
            critRate=None,
        ),
        BattleParticipantResponse(
            characterKey="chr_0004_pelica",
            characterName="佩丽卡",
            characterProfession="辅助",
            characterAvatarUrl=None,
            accountDisplayName="user-a",
            totalDamage=456_480,
            dps=7_608,
            rdps=54_916,
            maxHit=None,
            critRate=None,
        ),
    ]
    service._iter_boss_battles = lambda boss_slug, metric="dps": [battle]

    dps_ranking = service.get_boss_rankings("boss-test", "dps")
    rdps_ranking = service.get_boss_rankings("boss-test", "rdps")

    assert dps_ranking.rows[0].characterName == "糖糖"
    assert dps_ranking.rows[0].dps == 154_916
    assert rdps_ranking.rows[0].rdps == 154_916
