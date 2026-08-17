from __future__ import annotations

from typing import Any

_CURRENT_LOCALE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Common
        "app_title": "Endfield Logs Battle Analyzer",
        "app_window_title": "Endfield Logs Battle Analyzer",
        "app_name_full": "Endfield Logs Battle Analyzer",
        "ok": "OK",
        "cancel": "Cancel",
        "exit": "Exit",
        "save": "Save",
        "close": "Close",
        "refresh": "Refresh",
        "retry": "Retry",
        "delete": "Delete",
        "switch_on": "ON",
        "switch_off": "OFF",
        "enable_all": "Enable All",
        "disable_all": "Disable All",
        "error": "Error",
        "warning": "Warning",
        "info": "Notice",
        "none_dash": "-",

        # Navigation
        "nav_home": "Home",
        "nav_overlay": "Overlays",
        "nav_battle_log": "Combat Log",
        "nav_settings": "Settings",
        "nav_about": "About",

        # Home Page & Status & Squad Card
        "page_home_title": "Home",
        "page_home_subtitle": "Monitor connection state, current squad, and active overlay status.",
        "card_status_party_title": "Status & Squad",
        "status_program": "Parser Service",
        "status_game": "Game Client",
        "status_server": "Combat Server",
        "status_flow": "Current Session",
        "status_squad": "Current Squad",
        "squad_empty": "No squad data available",
        "squad_leader": "Leader",
        "status_not_started": "Not Started",
        "status_waiting_game": "Waiting for game client",
        "status_disconnected": "Disconnected",
        "status_running": "Running",
        "status_stopped_restart": "Stopped, please restart client",
        "status_game_running_restart": "Game already running, restart required",
        "status_waiting_session": "Waiting for new session",
        "status_game_detected": "Game client detected",
        "status_waiting_connect": "Waiting for game connection",
        "status_waiting_handshake": "Waiting for login handshake",
        "status_connected_battle": "Connected to combat server",

        # Overlays Status Card
        "card_overlay_status_title": "Overlays",
        "overlay_master_switch": "Master Switch",
        "overlay_master_switch_desc": "Enable or disable all overlays",
        "overlay_empty": "No overlays configured",
        "overlay_status_enabled": "Enabled",
        "overlay_status_locked": "Locked",
        "overlay_status_click": "Click-Through",
        "overlay_status_opacity": "Opacity",

        # Console Log Card
        "card_console_log_title": "Console Logs",

        # Overlays Management Page
        "page_overlay_title": "Overlays",
        "page_overlay_subtitle": "Manage built-in, local HTML, and remote web overlays.",
        "btn_add_url_overlay": "Add URL Overlay",
        "btn_add_file_overlay": "Select Local HTML",
        "btn_remove_overlay": "Delete Selected",
        "btn_enable_all_overlays": "Enable All",
        "btn_disable_all_overlays": "Disable All",
        "card_overlay_config_title": "Overlay Configuration",
        "field_overlay_name": "Name",
        "field_overlay_source_type": "Source Type",
        "field_overlay_source_url": "Source URL / Path",
        "field_overlay_enabled": "Enabled",
        "field_overlay_locked": "Lock Position",
        "field_overlay_click_through": "Mouse Click-Through",
        "field_overlay_opacity": "Opacity",
        "field_overlay_scale": "Scale",
        "field_overlay_geometry": "Geometry",
        "dialog_add_url_title": "Add URL Overlay",
        "dialog_add_url_prompt": "Please enter overlay URL:",
        "dialog_select_html_title": "Select Local Overlay Entry HTML",
        "overlay_name_online_default": "Web Overlay",

        # Overlay Builtin Names & Types
        "overlay_builtin_damage": "Damage Meter",
        "overlay_builtin_combo": "Combo CD Monitor",
        "overlay_builtin_buff": "Buff Monitor",
        "overlay_builtin_uid_mask": "UID Mask",
        "overlay_source_builtin": "Built-in Overlay",
        "overlay_source_file": "Local HTML",
        "overlay_source_url": "URL",

        # Combat Log Page
        "page_battle_log_title": "Combat Log",
        "page_battle_log_subtitle": "View aggregated combat statistics and battle records.",
        "card_record_list_title": "Record List",
        "btn_refresh_records": "Refresh Records",
        "record_count_fmt": "{count} total",
        "record_item_summary_fmt": "Dmg {damage}  DPS {dps}  Duration {duration}",
        "card_core_metrics_title": "Core Metrics",
        "metric_total_damage": "Total Damage",
        "metric_dps": "DPS",
        "metric_duration": "Duration",
        "metric_mvp": "MVP",
        "duration_seconds_unit": "s",
        "duration_seconds_fmt": "{duration:.2f} s",
        "card_damage_ranking_title": "Damage Breakdown",
        "col_rank": "Rank",
        "col_character": "Character",
        "col_total_damage": "Total Damage",
        "col_share": "Share",
        "col_crit_rate": "Crit Rate",
        "col_max_damage": "Max Hit",

        # Settings Page
        "page_settings_title": "Settings",
        "page_settings_subtitle": "Adjust interface language, appearance theme, log directory, and overlay hotkey.",
        "card_language_title": "Interface Language",
        "field_language": "Language",
        "language_hint": "Changes take effect immediately across all interfaces.",
        "card_theme_title": "Appearance",
        "field_theme_mode": "Theme Mode",
        "theme_system": "System Default",
        "theme_light": "Light",
        "theme_dark": "Dark",
        "theme_hint": "Follows operating system appearance by default.",
        "card_log_path_title": "Log File Path",
        "field_current_path": "Current Path",
        "field_dir_size": "Directory Size",
        "btn_select_log_dir": "Select Directory",
        "btn_refresh_dir_size": "Refresh Size",
        "dialog_select_log_dir_title": "Select Log Directory",
        "card_hotkey_title": "Global Hotkey",
        "field_toggle_overlays_hotkey": "Toggle Overlays",
        "hotkey_hint": "Toggles visibility for all enabled overlays. Default: Ctrl+O.",
        "hotkey_not_supported": "Global hotkeys are not supported on this platform.",
        "hotkey_invalid_format": "Invalid hotkey format, please choose another combination.",
        "hotkey_success_fmt": "Global hotkey registered: {hotkey}",
        "hotkey_conflict_fmt": "Hotkey conflict: {hotkey}",
        "card_combat_behavior_title": "Combat Behavior",
        "field_merge_multi_phase": "Merge Multi-Phase Enemy Battles",
        "merge_multi_phase_hint": "Note: When enabled, phase transition animations are included in combat duration, which will lower computed DPS.",
        "card_about_title": "About",
        "about_app_name": "Endfield Logs Battle Analyzer",
        "about_frontend": "UI Framework: PySide6-Fluent-Widgets",
        "about_version": "Version: V1.2.1",
        "about_group": "Community / QQ: 1101764944",
        "about_ws_port_fmt": "WS Port: {port}",
        "about_log_dir_fmt": "Log Directory: {dir}",

        # Wizard & Dialogs & Infobars
        "wizard_title": "First-Time Game Path Setup",
        "wizard_text": "Please select the Arknights: Endfield game directory or Endfield.exe.",
        "wizard_info": "The client will save this path and avoid scanning disks on startup.",
        "btn_choose_exe": "Select Endfield.exe",
        "btn_choose_dir": "Select Game Directory",
        "dialog_choose_exe_title": "Select Endfield.exe",
        "dialog_choose_dir_title": "Select Endfield Game Directory",
        "msg_invalid_game_dir_title": "Invalid Directory",
        "msg_invalid_game_dir_body": "Endfield.exe and GameAssembly.dll were not found in the selected location. Please select the game root directory.",
        "infobar_error_title": "Error",
        "infobar_notice_title": "Notice",
        "infobar_game_dir_missing": "Game installation directory not found. Please specify the Endfield Game directory.",
        "infobar_restart_game_notice": "This tool must be started before launching the game. Please restart the game.",
        "infobar_npcap_missing": "Npcap is required to capture and analyze network packets.",
        "dialog_service_crashed_title": "Service Error",
    },
    "zh": {
        # Common
        "app_title": "ZMDlogs 战斗分析器",
        "app_window_title": "ZMDlogs 战斗分析器",
        "app_name_full": "ZMDlogs 战斗分析器",
        "ok": "确定",
        "cancel": "取消",
        "exit": "退出",
        "save": "保存",
        "close": "关闭",
        "refresh": "刷新",
        "retry": "重试",
        "delete": "删除",
        "switch_on": "开",
        "switch_off": "关",
        "enable_all": "打开全部",
        "disable_all": "关闭全部",
        "error": "错误",
        "warning": "警告",
        "info": "提示",
        "none_dash": "-",

        # Navigation
        "nav_home": "首页",
        "nav_overlay": "悬浮窗",
        "nav_battle_log": "战斗日志",
        "nav_settings": "设置",
        "nav_about": "关于",

        # Home Page & Status & Squad Card
        "page_home_title": "首页",
        "page_home_subtitle": "查看连接状态、当前小队与悬浮窗运行情况。",
        "card_status_party_title": "状态和小队",
        "status_program": "解析服务",
        "status_game": "游戏客户端",
        "status_server": "服务器",
        "status_flow": "当前会话",
        "status_squad": "当前小队",
        "squad_empty": "暂无小队信息",
        "squad_leader": "队长",
        "status_not_started": "未启动",
        "status_waiting_game": "等待客户端运行",
        "status_disconnected": "未连接",
        "status_running": "运行中",
        "status_stopped_restart": "已停止，请重启主程序",
        "status_game_running_restart": "客户端已运行，需重开游戏",
        "status_waiting_session": "等待新会话",
        "status_game_detected": "已检测到客户端",
        "status_waiting_connect": "等待游戏连接",
        "status_waiting_handshake": "等待登录完成",
        "status_connected_battle": "已连接到战斗服务器",

        # Overlays Status Card
        "card_overlay_status_title": "悬浮窗",
        "overlay_master_switch": "总开关",
        "overlay_master_switch_desc": "开启或关闭所有悬浮窗",
        "overlay_empty": "暂无悬浮窗",
        "overlay_status_enabled": "开启",
        "overlay_status_locked": "锁定位置",
        "overlay_status_click": "鼠标穿透",
        "overlay_status_opacity": "透明度",

        # Console Log Card
        "card_console_log_title": "控制台日志",

        # Overlays Management Page
        "page_overlay_title": "悬浮窗",
        "page_overlay_subtitle": "管理内置、本地与在线悬浮窗。",
        "btn_add_url_overlay": "新增 URL 悬浮窗",
        "btn_add_file_overlay": "选择本地 HTML",
        "btn_remove_overlay": "删除选中",
        "btn_enable_all_overlays": "打开全部",
        "btn_disable_all_overlays": "关闭全部",
        "card_overlay_config_title": "悬浮窗配置",
        "field_overlay_name": "名称",
        "field_overlay_source_type": "来源类型",
        "field_overlay_source_url": "来源地址",
        "field_overlay_enabled": "启用",
        "field_overlay_locked": "锁定位置",
        "field_overlay_click_through": "鼠标穿透",
        "field_overlay_opacity": "透明度",
        "field_overlay_scale": "缩放",
        "field_overlay_geometry": "几何",
        "dialog_add_url_title": "新增 URL 悬浮窗",
        "dialog_add_url_prompt": "请输入悬浮窗 URL：",
        "dialog_select_html_title": "选择本地悬浮窗入口",
        "overlay_name_online_default": "在线悬浮窗",

        # Overlay Builtin Names & Types
        "overlay_builtin_damage": "伤害统计",
        "overlay_builtin_combo": "连携cd监控",
        "overlay_builtin_buff": "buff监控",
        "overlay_builtin_uid_mask": "UID遮挡",
        "overlay_source_builtin": "内置悬浮窗",
        "overlay_source_file": "本地 HTML",
        "overlay_source_url": "URL",

        # Combat Log Page
        "page_battle_log_title": "战斗日志",
        "page_battle_log_subtitle": "查看历史战斗的聚合统计信息。",
        "card_record_list_title": "记录列表",
        "btn_refresh_records": "刷新记录",
        "record_count_fmt": "共 {count} 条",
        "record_item_summary_fmt": "伤害 {damage}  DPS {dps}  时长 {duration}",
        "card_core_metrics_title": "核心数据",
        "metric_total_damage": "总伤害",
        "metric_dps": "DPS",
        "metric_duration": "战斗时长",
        "metric_mvp": "MVP",
        "duration_seconds_unit": "秒",
        "duration_seconds_fmt": "{duration:.2f} 秒",
        "card_damage_ranking_title": "伤害统计",
        "col_rank": "排名",
        "col_character": "角色",
        "col_total_damage": "总伤害",
        "col_share": "占比",
        "col_crit_rate": "暴击率",
        "col_max_damage": "最大伤害",

        # Settings Page
        "page_settings_title": "设置",
        "page_settings_subtitle": "调整主题、语言、日志目录和悬浮窗快捷键。",
        "card_language_title": "界面语言",
        "field_language": "语言",
        "language_hint": "切换语言后立即生效。",
        "card_theme_title": "主题",
        "field_theme_mode": "主题模式",
        "theme_system": "跟随系统",
        "theme_light": "亮色",
        "theme_dark": "暗色",
        "theme_hint": "默认跟随系统主题。",
        "card_log_path_title": "日志文件路径",
        "field_current_path": "当前路径",
        "field_dir_size": "目录大小",
        "btn_select_log_dir": "选择日志目录",
        "btn_refresh_dir_size": "刷新文件夹大小",
        "dialog_select_log_dir_title": "选择日志目录",
        "card_hotkey_title": "快捷键",
        "field_toggle_overlays_hotkey": "切换悬浮窗",
        "hotkey_hint": "用于开启或隐藏全部悬浮窗，默认 Ctrl+O。",
        "hotkey_not_supported": "当前平台不支持全局热键",
        "hotkey_invalid_format": "快捷键格式无效，请换一个组合键",
        "hotkey_success_fmt": "全局热键设定成功：{hotkey}",
        "hotkey_conflict_fmt": "快捷键冲突：{hotkey}",
        "card_combat_behavior_title": "战斗行为",
        "field_merge_multi_phase": "合并多阶段敌人的战斗",
        "merge_multi_phase_hint": "注意：开启此选项后，转阶段的动画也会被计入战斗时长，这会导致您的DPS降低。",
        "card_about_title": "关于",
        "about_app_name": "ZMDlogs 战斗分析器",
        "about_frontend": "前端：PySide6-Fluent-Widgets",
        "about_version": "版本：V1.2.1",
        "about_group": "开发/交流群：1101764944",
        "about_ws_port_fmt": "WS 端口: {port}",
        "about_log_dir_fmt": "日志目录: {dir}",

        # Wizard & Dialogs & Infobars
        "wizard_title": "首次设置游戏路径",
        "wizard_text": "请选择终末地游戏目录或 Endfield.exe。",
        "wizard_info": "客户端会保存这个路径，后续启动不会自动扫描磁盘。",
        "btn_choose_exe": "选择 Endfield.exe",
        "btn_choose_dir": "选择游戏目录",
        "dialog_choose_exe_title": "选择 Endfield.exe",
        "dialog_choose_dir_title": "选择 Endfield Game 目录",
        "msg_invalid_game_dir_title": "目录无效",
        "msg_invalid_game_dir_body": "所选位置没有同时找到 Endfield.exe 和 GameAssembly.dll，请重新选择游戏根目录。",
        "infobar_error_title": "错误",
        "infobar_notice_title": "提示",
        "infobar_game_dir_missing": "没有找到游戏安装目录，请手动指定 Endfield Game 目录",
        "infobar_restart_game_notice": "需要先开启本工具再开启游戏，请重开游戏。",
        "infobar_npcap_missing": "需要先安装 NpCap 才能分析网络包",
        "dialog_service_crashed_title": "服务异常",
    },
}

_BUILTIN_NAME_KEYS = {
    "damage": "overlay_builtin_damage",
    "combo_skill": "overlay_builtin_combo",
    "buff": "overlay_builtin_buff",
    "uid_mask": "overlay_builtin_uid_mask",
}

_LEGACY_BUILTIN_NAME_MAP = {
    "伤害统计": "damage",
    "Damage Meter": "damage",
    "连携cd监控": "combo_skill",
    "Combo CD Monitor": "combo_skill",
    "buff监控": "buff",
    "Buff Monitor": "buff",
    "UID遮挡": "uid_mask",
    "UID Mask": "uid_mask",
    "悬浮窗": "damage",
    "内置悬浮窗": "damage",
}


def set_locale(locale: str) -> None:
    global _CURRENT_LOCALE
    _CURRENT_LOCALE = "zh" if str(locale).strip().lower().startswith("zh") else "en"


def get_locale() -> str:
    return _CURRENT_LOCALE


def tr(key: str, **kwargs: Any) -> str:
    lang = _CURRENT_LOCALE
    template = TRANSLATIONS.get(lang, {}).get(key)
    if template is None:
        template = TRANSLATIONS.get("en", {}).get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


def format_duration(duration_ms: int) -> str:
    seconds = max(0.0, duration_ms / 1000.0)
    return tr("duration_seconds_fmt", duration=seconds)


def get_builtin_overlay_display_name(source_value: str, fallback_name: str = "") -> str:
    key = _BUILTIN_NAME_KEYS.get(source_value)
    if key:
        return tr(key)
    source_val = _LEGACY_BUILTIN_NAME_MAP.get(fallback_name)
    if source_val:
        key = _BUILTIN_NAME_KEYS.get(source_val)
        if key:
            return tr(key)
    return fallback_name or tr("overlay_builtin_damage")


def get_theme_labels() -> dict[str, str]:
    return {
        "system": tr("theme_system"),
        "light": tr("theme_light"),
        "dark": tr("theme_dark"),
    }
