from app.services.public_data import DemoPublicDataService, _is_registrable_boss_identity


def _register(service: DemoPublicDataService, *, boss_slug: str, boss_name: str, dungeon_name: str) -> None:
    service._ensure_boss_catalog_entry(
        boss_key="eny_9999_test",
        boss_slug=boss_slug,
        boss_name=boss_name,
        dungeon_name=dungeon_name,
        roster_keys=["chr_0027_tangtang"],
        uploader_nickname="tester",
        duration_ms=60_000,
        lead_dps=1000.0,
        lead_rdps=1000.0,
    )


def test_unknown_dungeon_upload_does_not_pollute_catalog() -> None:
    service = DemoPublicDataService()
    _register(service, boss_slug="unknown_dungeon", boss_name="未知副本", dungeon_name="未知副本")
    assert "unknown_dungeon" not in service.bosses_by_slug


def test_raw_enemy_key_names_do_not_pollute_catalog() -> None:
    service = DemoPublicDataService()
    _register(service, boss_slug="mystery_stage", boss_name="eny_0123_something", dungeon_name="未知副本")
    assert "mystery_stage" not in service.bosses_by_slug

    _register(service, boss_slug="", boss_name="测试首领", dungeon_name="测试副本")
    assert "" not in service.bosses_by_slug


def test_legit_new_dungeon_still_auto_registers() -> None:
    service = DemoPublicDataService()
    _register(service, boss_slug="indie_hard099_s", boss_name="新副本·苦难", dungeon_name="影拓丰碑9期")
    assert "indie_hard099_s" in service.bosses_by_slug
    assert service.bosses_by_slug["indie_hard099_s"].name == "新副本·苦难"

    # raw boss_name is tolerated when dungeon_name is usable (display falls back to dungeon)
    _register(service, boss_slug="indie_hard098_s", boss_name="eny_0200_newboss", dungeon_name="影拓丰碑9期")
    assert "indie_hard098_s" in service.bosses_by_slug


def test_is_registrable_boss_identity_matrix() -> None:
    assert _is_registrable_boss_identity("slug", "正常名字", "正常副本")
    assert _is_registrable_boss_identity("slug", "", "正常副本")
    assert _is_registrable_boss_identity("slug", "正常名字", "")
    assert not _is_registrable_boss_identity("", "正常名字", "正常副本")
    assert not _is_registrable_boss_identity("unknown_dungeon", "正常名字", "正常副本")
    assert not _is_registrable_boss_identity("slug", "eny_0001_x", "未知副本")
    assert not _is_registrable_boss_identity("slug", "", "")
    assert not _is_registrable_boss_identity("slug", "未知副本", "未知副本")
