from __future__ import annotations

import json
from pathlib import Path
import pytest

from endfield_pcap.i18n import (
    TRANSLATIONS,
    format_duration,
    get_builtin_overlay_display_name,
    get_locale,
    get_theme_labels,
    set_locale,
    tr,
)
from endfield_pcap.gui_config import (
    AppConfig,
    default_service_config,
    load_app_config,
    save_app_config,
    _normalize_language,
)


def test_translation_key_parity() -> None:
    en_keys = set(TRANSLATIONS["en"].keys())
    zh_keys = set(TRANSLATIONS["zh"].keys())
    assert en_keys == zh_keys, f"Keys missing in zh: {en_keys - zh_keys}, Keys missing in en: {zh_keys - en_keys}"


def test_default_locale_is_english() -> None:
    set_locale("en")
    assert get_locale() == "en"
    assert tr("app_title") == "Endfield Logs Battle Analyzer"
    assert tr("nav_home") == "Home"
    assert tr("nav_overlay") == "Overlays"
    assert tr("nav_battle_log") == "Combat Log"
    assert tr("nav_settings") == "Settings"


def test_switch_locale_to_chinese() -> None:
    set_locale("zh")
    assert get_locale() == "zh"
    assert tr("app_title") == "ZMDlogs 战斗分析器"
    assert tr("nav_home") == "首页"
    assert tr("nav_overlay") == "悬浮窗"
    assert tr("nav_battle_log") == "战斗日志"
    assert tr("nav_settings") == "设置"
    set_locale("en")


def test_format_duration_i18n() -> None:
    set_locale("en")
    assert format_duration(1500) == "1.50 s"
    set_locale("zh")
    assert format_duration(1500) == "1.50 秒"
    set_locale("en")


def test_get_builtin_overlay_display_name_i18n() -> None:
    set_locale("en")
    assert get_builtin_overlay_display_name("damage", "伤害统计") == "Damage Meter"
    assert get_builtin_overlay_display_name("combo_skill", "连携cd监控") == "Combo CD Monitor"
    assert get_builtin_overlay_display_name("buff", "buff监控") == "Buff Monitor"
    assert get_builtin_overlay_display_name("uid_mask", "UID遮挡") == "UID Mask"
    assert get_builtin_overlay_display_name("custom", "My Overlay") == "My Overlay"

    set_locale("zh")
    assert get_builtin_overlay_display_name("damage", "Damage Meter") == "伤害统计"
    assert get_builtin_overlay_display_name("combo_skill", "Combo CD Monitor") == "连携cd监控"
    assert get_builtin_overlay_display_name("buff", "Buff Monitor") == "buff监控"
    assert get_builtin_overlay_display_name("uid_mask", "UID Mask") == "UID遮挡"
    set_locale("en")


def test_get_theme_labels_i18n() -> None:
    set_locale("en")
    en_labels = get_theme_labels()
    assert en_labels["system"] == "System Default"
    assert en_labels["light"] == "Light"
    assert en_labels["dark"] == "Dark"

    set_locale("zh")
    zh_labels = get_theme_labels()
    assert zh_labels["system"] == "跟随系统"
    assert zh_labels["light"] == "亮色"
    assert zh_labels["dark"] == "暗色"
    set_locale("en")


def test_normalize_language() -> None:
    assert _normalize_language("en") == "en"
    assert _normalize_language("EN") == "en"
    assert _normalize_language("english") == "en"
    assert _normalize_language("zh") == "zh"
    assert _normalize_language("zh-CN") == "zh"
    assert _normalize_language("ZH") == "zh"
    assert _normalize_language(None) == "en"
    assert _normalize_language("") == "en"


def test_app_config_language_persistence(tmp_path: Path) -> None:
    config_file = tmp_path / "settings.json"
    config = AppConfig(service=default_service_config(), language="en")
    save_app_config(config, config_file)

    loaded = load_app_config(config_file)
    assert loaded.language == "en"

    loaded.language = "zh"
    save_app_config(loaded, config_file)

    reloaded = load_app_config(config_file)
    assert reloaded.language == "zh"

    # Verify JSON structure
    raw = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw["language"] == "zh"
