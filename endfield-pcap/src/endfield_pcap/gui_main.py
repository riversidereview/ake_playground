from __future__ import annotations

import asyncio
import ctypes
from datetime import datetime
import json
import logging
import queue
import sys
import threading
import traceback
import uuid
from ctypes import wintypes
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QKeySequenceEdit,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    FluentIcon as FIF,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    HeaderCardWidget,
    ImageLabel,
    LineEdit,
    ListWidget,
    NavigationItemPosition,
    GroupHeaderCardWidget,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    Slider,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    Theme,
    HyperlinkLabel,
    isDarkTheme,
    setFont,
    setTheme,
)

from .gui_config import AppConfig, default_config_path, load_app_config, save_app_config
from .i18n import (
    format_duration,
    get_builtin_overlay_display_name,
    get_locale,
    get_theme_labels,
    set_locale,
    tr,
)
from .logging_utils import configure_logging
from .models import FlowKey, OverlayEntry, OverlayGeometry, OverlaySourceType, RuntimeMetrics, ServiceObserver, ServiceState, SquadMemberPayload
from .npcap import has_npcap
from .overlay_host import OverlayManager
from .record_parser import CombatRecord, load_combat_records
from .runtime_paths import app_root, bundle_root
from .service import DamageLogService, ServiceConfig

LOGGER = logging.getLogger(__name__)
ROOT = bundle_root()
APP_ICON_PNG = ROOT / "icon.png"
APP_ICON_ICO = ROOT / "icon.ico"
ICON_DIR = ROOT / "icon" / "Texture2D"
ACTOR_IMAGE_TABLE = ROOT / "jsondata" / "ActorImageTable.json"
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
APP_USER_MODEL_ID = "ZMDlogs.endfield_pcap"
GLOBAL_HOTKEY_ID = 0xB100
USER32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None


def _app_icon_path() -> Path | None:
    if APP_ICON_ICO.exists():
        return APP_ICON_ICO
    if APP_ICON_PNG.exists():
        return APP_ICON_PNG
    return None


class SingleHotkeyEdit(QKeySequenceEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._replace_pending = False

    def focusInEvent(self, event) -> None:  # type: ignore[override]
        self._replace_pending = True
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:  # type: ignore[override]
        self._replace_pending = False
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if self._replace_pending:
            self.clear()
            self._replace_pending = False
        super().keyPressEvent(event)


class QtLogHandler(logging.Handler):
    def __init__(self, sink: "queue.Queue[tuple[str, object]]") -> None:
        super().__init__()
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.put_nowait(("log", self.format(record)))
        except Exception:
            return


class ServiceController:
    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._service: DamageLogService | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        observer = ServiceObserver(
            on_state_change=lambda state, session_id, flow: self.queue.put(
                ("state", {"state": state, "session_id": session_id, "flow": flow})
            ),
            on_runtime_metrics=lambda metrics, pcap_stats, flow: self.queue.put(
                ("metrics", {"metrics": metrics, "pcap_stats": pcap_stats, "flow": flow})
            ),
            on_event=lambda event: self.queue.put(("event", event))
            if str(event.get("type", "")) == "SC_SELF_SCENE_INFO"
            else None,
        )
        self._service = DamageLogService(self.config, observer=observer)

        def runner() -> None:
            try:
                assert self._service is not None
                asyncio.run(self._service.run())
            except BaseException as exc:  # noqa: BLE001
                self.queue.put(("error", exc))
            finally:
                self.queue.put(("stopped", None))

        self._thread = threading.Thread(target=runner, name="damage-service", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._service is not None:
            self._service.request_stop()

    def join(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)


def _load_avatar_index() -> dict[str, Path]:
    if not ACTOR_IMAGE_TABLE.exists():
        return {}
    payload = json.loads(ACTOR_IMAGE_TABLE.read_text(encoding="utf-8"))
    result: dict[str, Path] = {}
    for templateid, item in payload.items():
        avatar = item.get("avatarPath")
        if avatar:
            result[str(templateid)] = ICON_DIR / f"{avatar}.png"
    return result


def _theme_from_mode(mode: str) -> Theme:
    normalized = str(mode or "system").strip().lower()
    if normalized == "light":
        return Theme.LIGHT
    if normalized == "dark":
        return Theme.DARK
    return Theme.AUTO


def _overlay_source_type_label(source_type: OverlaySourceType) -> str:
    if source_type == OverlaySourceType.BUILTIN:
        return tr("overlay_source_builtin")
    if source_type == OverlaySourceType.FILE:
        return tr("overlay_source_file")
    if source_type == OverlaySourceType.URL:
        return tr("overlay_source_url")
    return source_type.value


def _is_valid_game_dir(path: Path | None) -> bool:
    if path is None:
        return False
    target = Path(path)
    return (target / "GameAssembly.dll").exists() and (target / "Endfield.exe").exists()


def _normalize_game_dir_selection(raw_path: str) -> Path | None:
    if not raw_path:
        return None
    try:
        target = Path(raw_path).expanduser().resolve()
    except OSError:
        return None
    if target.is_file():
        target = target.parent
    return target


def _select_game_directory_from_dialog(parent: QWidget | None, start_dir: Path, *, select_exe: bool) -> Path | None:
    if select_exe:
        selected, _ = QFileDialog.getOpenFileName(
            parent,
            tr("dialog_choose_exe_title"),
            str(start_dir),
            "Endfield.exe (Endfield.exe);;Executable Files (*.exe);;All Files (*)",
        )
    else:
        selected = QFileDialog.getExistingDirectory(parent, tr("dialog_choose_dir_title"), str(start_dir))
    return _normalize_game_dir_selection(selected)


def _run_game_directory_wizard(app_config: AppConfig, config_path: Path, parent: QWidget | None = None) -> bool:
    start_dir = app_config.service.dll_dir if app_config.service.dll_dir else ROOT
    while True:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(tr("wizard_title"))
        box.setText(tr("wizard_text"))
        box.setInformativeText(tr("wizard_info"))
        exe_button = box.addButton(tr("btn_choose_exe"), QMessageBox.ButtonRole.AcceptRole)
        dir_button = box.addButton(tr("btn_choose_dir"), QMessageBox.ButtonRole.ActionRole)
        cancel_button = box.addButton(tr("btn_exit"), QMessageBox.ButtonRole.RejectRole)
        box.exec()

        clicked = box.clickedButton()
        if clicked == cancel_button:
            return False

        selected_dir = _select_game_directory_from_dialog(
            parent,
            start_dir,
            select_exe=clicked == exe_button,
        )
        if selected_dir is None:
            continue
        start_dir = selected_dir
        if not _is_valid_game_dir(selected_dir):
            QMessageBox.warning(
                parent,
                tr("msg_invalid_game_dir_title"),
                tr("msg_invalid_game_dir_body"),
            )
            continue

        app_config.service.dll_dir = selected_dir
        app_config.service.game_exe = "Endfield.exe"
        save_app_config(app_config, config_path)
        return True


def _qt_key_to_vk(key: Qt.Key) -> int | None:
    key_value = int(key)
    if int(Qt.Key.Key_0) <= key_value <= int(Qt.Key.Key_9):
        return key_value
    if int(Qt.Key.Key_A) <= key_value <= int(Qt.Key.Key_Z):
        return key_value
    if int(Qt.Key.Key_F1) <= key_value <= int(Qt.Key.Key_F24):
        return 0x70 + (key_value - int(Qt.Key.Key_F1))
    explicit_map = {
        int(Qt.Key.Key_Space): 0x20,
        int(Qt.Key.Key_Tab): 0x09,
        int(Qt.Key.Key_Backspace): 0x08,
        int(Qt.Key.Key_Return): 0x0D,
        int(Qt.Key.Key_Enter): 0x0D,
        int(Qt.Key.Key_Escape): 0x1B,
        int(Qt.Key.Key_Left): 0x25,
        int(Qt.Key.Key_Up): 0x26,
        int(Qt.Key.Key_Right): 0x27,
        int(Qt.Key.Key_Down): 0x28,
        int(Qt.Key.Key_Home): 0x24,
        int(Qt.Key.Key_End): 0x23,
        int(Qt.Key.Key_PageUp): 0x21,
        int(Qt.Key.Key_PageDown): 0x22,
        int(Qt.Key.Key_Insert): 0x2D,
        int(Qt.Key.Key_Delete): 0x2E,
        int(Qt.Key.Key_Minus): 0xBD,
        int(Qt.Key.Key_Equal): 0xBB,
        int(Qt.Key.Key_Comma): 0xBC,
        int(Qt.Key.Key_Period): 0xBE,
        int(Qt.Key.Key_Slash): 0xBF,
        int(Qt.Key.Key_Semicolon): 0xBA,
        int(Qt.Key.Key_Apostrophe): 0xDE,
        int(Qt.Key.Key_BracketLeft): 0xDB,
        int(Qt.Key.Key_BracketRight): 0xDD,
        int(Qt.Key.Key_Backslash): 0xDC,
        int(Qt.Key.Key_QuoteLeft): 0xC0,
    }
    return explicit_map.get(key_value)


def _portable_hotkey_to_native(hotkey: str) -> tuple[int, int] | None:
    sequence = QKeySequence(hotkey or "")
    combo = sequence[0]
    if combo.key() == Qt.Key.Key_unknown:
        return None
    modifiers = 0
    if combo.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
        modifiers |= MOD_CONTROL
    if combo.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
        modifiers |= MOD_ALT
    if combo.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= MOD_SHIFT
    if combo.keyboardModifiers() & Qt.KeyboardModifier.MetaModifier:
        modifiers |= MOD_WIN
    vk = _qt_key_to_vk(combo.key())
    if vk is None:
        return None
    return modifiers, vk


def _format_directory_size(size_bytes: int) -> str:
    value = float(max(0, size_bytes))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while value >= 1024.0 and unit_index < len(units) - 1:
        value /= 1024.0
        unit_index += 1
    if unit_index == 0:
        return f"{int(value)} {units[unit_index]}"
    return f"{value:.2f} {units[unit_index]}"


def _directory_size(path: Path) -> int:
    total = 0
    try:
        if not path.exists():
            return 0
        for child in path.rglob("*"):
            try:
                if child.is_file():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _has_combat_logs(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        for child in path.rglob("session_*.ndjson"):
            try:
                if child.is_file() and child.stat().st_size > 0:
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _resolve_log_dir(preferred: Path) -> Path:
    candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in (
        preferred,
        app_root() / "logs",
        bundle_root() / "logs",
        Path.cwd() / "logs",
    ):
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    for candidate in candidates:
        if _has_combat_logs(candidate):
            return candidate.resolve()
    return preferred.resolve()


class InterfacePage(ScrollArea):
    def __init__(self, object_name: str, title_key: str, subtitle_key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.title_key = title_key
        self.subtitle_key = subtitle_key
        self.setWidgetResizable(True)
        container = QWidget(self)
        self.container = container
        self.setWidget(container)

        self.content_layout = QVBoxLayout(container)
        self.content_layout.setContentsMargins(32, 28, 32, 28)
        self.content_layout.setSpacing(20)

    def retranslate_ui(self) -> None:
        pass


class StatusPartyCard(HeaderCardWidget):
    def __init__(self, avatar_index: dict[str, Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(tr("card_status_party_title"))
        self.avatar_index = avatar_index

        wrapper = QWidget(self.view)
        self.viewLayout.addWidget(wrapper)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.program_status = CaptionLabel(tr("status_not_started"), wrapper)
        self.game_status = CaptionLabel(tr("status_waiting_game"), wrapper)
        self.server_status = CaptionLabel(tr("status_disconnected"), wrapper)
        self.flow_status = CaptionLabel("-", wrapper)

        self.row_labels: list[StrongBodyLabel] = []
        self._row_keys = ["status_program", "status_game", "status_server", "status_flow"]
        for key, value in zip(self._row_keys, (self.program_status, self.game_status, self.server_status, self.flow_status)):
            row = QHBoxLayout()
            labelname = StrongBodyLabel(tr(key), wrapper)
            labelname.setFixedWidth(130)
            self.row_labels.append(labelname)
            row.addWidget(labelname)
            row.addWidget(value)
            row.addStretch()
            row.setSpacing(20)
            row.setContentsMargins(30, 0, 0, 0)
            layout.addLayout(row)

        self.squad_title = StrongBodyLabel(tr("status_squad"), wrapper)
        self.squad_title.setFixedWidth(130)
        self.squad_row = QHBoxLayout()
        self.squad_row.addWidget(self.squad_title)
        self.squad_row.setSpacing(20)
        self.squad_row.setContentsMargins(30, 0, 0, 0)
        layout.addLayout(self.squad_row)
        self._current_members: list[SquadMemberPayload] = []

    def set_status(self, program: str, game: str, server: str, flow: str) -> None:
        self.program_status.setText(program)
        self.game_status.setText(game)
        self.server_status.setText(server)
        self.flow_status.setText(flow)

    def set_squad_members(self, members: list[SquadMemberPayload]) -> None:
        self._current_members = members
        while self.squad_row.count():
            item = self.squad_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.squad_row.addWidget(self.squad_title)
        if not members:
            self.squad_row.addWidget(CaptionLabel(tr("squad_empty"), self))
            self.squad_row.addStretch()
            return
        for member in sorted(members, key=lambda item: item.squad_index):
            tile = QWidget(self)
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(0, 0, 0, 0)
            tile_layout.setSpacing(6)
            avatar_path = self.avatar_index.get(member.templateid or "")
            if avatar_path and avatar_path.exists():
                avatar = ImageLabel(str(avatar_path), tile)
            else:
                avatar = ImageLabel(tile)
                avatar.setImage(QPixmap())
                avatar.setText((member.display_name or "?")[:1])
            avatar.setFixedSize(56, 56)
            avatar.setBorderRadius(12, 12, 12, 12)
            avatar.setScaledContents(True)
            name = CaptionLabel(member.display_name or member.templateid or str(member.battle_inst_id), tile)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setWordWrap(True)
            badge_text = tr("squad_leader") if member.is_leader else f"#{member.squad_index + 1}"
            badge = CaptionLabel(badge_text, tile)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile_layout.addWidget(avatar, 0, Qt.AlignmentFlag.AlignCenter)
            tile_layout.addWidget(name)
            tile_layout.addWidget(badge)
            self.squad_row.addWidget(tile)
        self.squad_row.addStretch()

    def retranslate_ui(self) -> None:
        self.setTitle(tr("card_status_party_title"))
        for label, key in zip(self.row_labels, self._row_keys):
            label.setText(tr(key))
        self.squad_title.setText(tr("status_squad"))
        self.set_squad_members(self._current_members)


class OverlayStatusCard(GroupHeaderCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(tr("card_overlay_status_title"))
        self.visibility_switch = SwitchButton()
        self.visibility_switch.setOnText(tr("switch_on"))
        self.visibility_switch.setOffText(tr("switch_off"))
        self.group_item = self.addGroup(
            FIF.POWER_BUTTON,
            tr("overlay_master_switch"),
            tr("overlay_master_switch_desc"),
            self.visibility_switch,
        )
        self.group_item.setSeparatorVisible(True)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(10)
        self.rows_layout.setContentsMargins(0, 20, 0, 20)
        self.vBoxLayout.addLayout(self.rows_layout)
        self._entries: list[OverlayEntry] = []

    def set_entries(self, entries: list[OverlayEntry]) -> None:
        self._entries = entries
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not entries:
            self.rows_layout.addWidget(CaptionLabel(tr("overlay_empty"), self))
            return
        for entry in entries:
            row = QWidget(self)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(20, 8, 20, 8)
            disp_name = (
                get_builtin_overlay_display_name(entry.source_value, entry.name)
                if entry.source_type == OverlaySourceType.BUILTIN
                else entry.name
            )
            row_layout.addWidget(StrongBodyLabel(disp_name, row))
            row_layout.addStretch()
            row_layout.setSpacing(10)
            row_layout.addWidget(CaptionLabel(f"{tr('overlay_status_enabled')}{'√' if entry.enabled else '×'}", row))
            row_layout.addWidget(CaptionLabel(f"{tr('overlay_status_locked')}{'√' if entry.locked else '×'}", row))
            row_layout.addWidget(CaptionLabel(f"{tr('overlay_status_click')}{'√' if entry.click_through else '×'}", row))
            row_layout.addWidget(CaptionLabel(f"{tr('overlay_status_opacity')}:{int(round(entry.opacity * 100))}%", row))
            self.rows_layout.addWidget(row)

    def set_all_visible(self, enabled: bool) -> None:
        self.visibility_switch.blockSignals(True)
        self.visibility_switch.setChecked(enabled)
        self.visibility_switch.blockSignals(False)

    def retranslate_ui(self) -> None:
        self.setTitle(tr("card_overlay_status_title"))
        self.visibility_switch.setOnText(tr("switch_on"))
        self.visibility_switch.setOffText(tr("switch_off"))
        if hasattr(self.group_item, "titleLabel"):
            self.group_item.titleLabel.setText(tr("overlay_master_switch"))
        if hasattr(self.group_item, "contentLabel"):
            self.group_item.contentLabel.setText(tr("overlay_master_switch_desc"))
        self.set_entries(self._entries)


class LogCard(HeaderCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTitle(tr("card_console_log_title"))
        self.log_view = QPlainTextEdit(self.view)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(800)
        self.log_view.setMinimumHeight(320)
        self.viewLayout.addWidget(self.log_view)

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def retranslate_ui(self) -> None:
        self.setTitle(tr("card_console_log_title"))


class HomePage(InterfacePage):
    def __init__(self, avatar_index: dict[str, Path], parent: QWidget | None = None) -> None:
        super().__init__("homeInterface", "page_home_title", "page_home_subtitle", parent)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.status_card = StatusPartyCard(avatar_index, self)
        self.overlay_status_card = OverlayStatusCard(self)
        self.log_card = LogCard(self)
        grid.addWidget(self.status_card, 0, 0)
        grid.addWidget(self.overlay_status_card, 0, 1)
        grid.addWidget(self.log_card, 1, 0, 1, 2)
        self.log_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.content_layout.addLayout(grid)

    def retranslate_ui(self) -> None:
        self.status_card.retranslate_ui()
        self.overlay_status_card.retranslate_ui()
        self.log_card.retranslate_ui()


class OverlayPage(InterfacePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("overlayInterface", "page_overlay_title", "page_overlay_subtitle", parent)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self.add_url_btn = PrimaryPushButton(tr("btn_add_url_overlay"), actions)
        self.add_file_btn = PushButton(tr("btn_add_file_overlay"), actions)
        self.remove_btn = PushButton(tr("btn_remove_overlay"), actions)
        self.enable_all_btn = PushButton(tr("btn_enable_all_overlays"), actions)
        self.disable_all_btn = PushButton(tr("btn_disable_all_overlays"), actions)
        for button in (self.add_url_btn, self.add_file_btn, self.remove_btn, self.enable_all_btn, self.disable_all_btn):
            actions_layout.addWidget(button)
        actions_layout.addStretch()
        self.content_layout.addWidget(actions, alignment=Qt.AlignmentFlag.AlignTop)

        self.card = HeaderCardWidget(tr("card_overlay_config_title"), self)
        self.content_layout.addWidget(self.card, 1)
        self.content_layout.addStretch()
        splitter = QSplitter(self.card)
        self.card.viewLayout.addWidget(splitter, 1)

        self.overlay_list = ListWidget(splitter)
        splitter.addWidget(self.overlay_list)

        details = QWidget(splitter)
        splitter.addWidget(details)
        splitter.setSizes([100, 400])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        self.form = QFormLayout(details)
        self.name_edit = LineEdit(details)
        self.source_type_label = CaptionLabel("-", details)
        self.source_value_edit = LineEdit(details)
        self.enabled_switch = SwitchButton(details)
        self.enabled_switch.setOnText(tr("switch_on"))
        self.enabled_switch.setOffText(tr("switch_off"))
        self.locked_switch = SwitchButton(details)
        self.locked_switch.setOnText(tr("switch_on"))
        self.locked_switch.setOffText(tr("switch_off"))
        self.click_switch = SwitchButton(details)
        self.click_switch.setOnText(tr("switch_on"))
        self.click_switch.setOffText(tr("switch_off"))
        self.opacity_slider = Slider(Qt.Orientation.Horizontal, details)
        self.opacity_slider.setRange(10, 100)
        self.opacity_value = CaptionLabel("100%", details)
        opacity_row = QWidget(details)
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity_value)
        self.scale_slider = Slider(Qt.Orientation.Horizontal, details)
        self.scale_slider.setRange(50, 300)
        self.scale_value = CaptionLabel("100%", details)
        scale_row = QWidget(details)
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.addWidget(self.scale_slider, 1)
        scale_layout.addWidget(self.scale_value)
        self.geometry_label = CaptionLabel("-", details)

        self._row_labels = [
            ("field_overlay_name", self.name_edit),
            ("field_overlay_source_type", self.source_type_label),
            ("field_overlay_source_url", self.source_value_edit),
            ("field_overlay_enabled", self.enabled_switch),
            ("field_overlay_locked", self.locked_switch),
            ("field_overlay_click_through", self.click_switch),
            ("field_overlay_opacity", opacity_row),
            ("field_overlay_scale", scale_row),
            ("field_overlay_geometry", self.geometry_label),
        ]
        for key, widget in self._row_labels:
            self.form.addRow(tr(key), widget)
        self.form.setSpacing(15)
        self._updating = False
        self._entries: list[OverlayEntry] = []

    def selected_entry_id(self) -> str | None:
        item = self.overlay_list.currentItem()
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def set_entries(self, entries: list[OverlayEntry]) -> None:
        self._entries = entries
        selected = self.selected_entry_id()
        self.overlay_list.clear()
        for entry in entries:
            disp_name = (
                get_builtin_overlay_display_name(entry.source_value, entry.name)
                if entry.source_type == OverlaySourceType.BUILTIN
                else entry.name
            )
            item = self.overlay_list.addItem(disp_name)
            real_item = self.overlay_list.item(self.overlay_list.count() - 1)
            real_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            if entry.id == selected:
                self.overlay_list.setCurrentItem(real_item)
        if self.overlay_list.currentItem() is None and self.overlay_list.count() > 0:
            self.overlay_list.setCurrentRow(0)

    def show_entry(self, entry: OverlayEntry | None) -> None:
        self._updating = True
        try:
            if entry is None:
                self.name_edit.clear()
                self.source_type_label.setText("-")
                self.source_value_edit.clear()
                self.enabled_switch.setChecked(False)
                self.locked_switch.setChecked(False)
                self.click_switch.setChecked(False)
                self.opacity_slider.setValue(100)
                self.opacity_value.setText("100%")
                self.scale_slider.setValue(100)
                self.scale_value.setText("100%")
                self.geometry_label.setText("-")
                self.remove_btn.setEnabled(False)
                self.source_value_edit.setReadOnly(True)
                return
            disp_name = (
                get_builtin_overlay_display_name(entry.source_value, entry.name)
                if entry.source_type == OverlaySourceType.BUILTIN
                else entry.name
            )
            self.name_edit.setText(disp_name)
            self.name_edit.setReadOnly(entry.source_type == OverlaySourceType.BUILTIN)
            self.source_type_label.setText(_overlay_source_type_label(entry.source_type))
            self.source_value_edit.setText(entry.source_value)
            self.source_value_edit.setReadOnly(entry.source_type != OverlaySourceType.URL)
            self.enabled_switch.setChecked(entry.enabled)
            self.locked_switch.setChecked(entry.locked)
            self.click_switch.setChecked(entry.click_through)
            self.opacity_slider.setValue(int(round(entry.opacity * 100)))
            self.opacity_value.setText(f"{int(round(entry.opacity * 100))}%")
            self.scale_slider.setValue(int(round(entry.scale * 100)))
            self.scale_value.setText(f"{int(round(entry.scale * 100))}%")
            geometry = entry.geometry
            self.geometry_label.setText("-" if geometry is None else f"x={geometry.x}, y={geometry.y}, {geometry.width}x{geometry.height}")
            self.remove_btn.setEnabled(entry.source_type != OverlaySourceType.BUILTIN)
        finally:
            self._updating = False

    def retranslate_ui(self) -> None:
        self.add_url_btn.setText(tr("btn_add_url_overlay"))
        self.add_file_btn.setText(tr("btn_add_file_overlay"))
        self.remove_btn.setText(tr("btn_remove_overlay"))
        self.enable_all_btn.setText(tr("btn_enable_all_overlays"))
        self.disable_all_btn.setText(tr("btn_disable_all_overlays"))
        self.card.setTitle(tr("card_overlay_config_title"))
        self.enabled_switch.setOnText(tr("switch_on"))
        self.enabled_switch.setOffText(tr("switch_off"))
        self.locked_switch.setOnText(tr("switch_on"))
        self.locked_switch.setOffText(tr("switch_off"))
        self.click_switch.setOnText(tr("switch_on"))
        self.click_switch.setOffText(tr("switch_off"))
        for row, (key, _) in enumerate(self._row_labels):
            label_item = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if label_item and label_item.widget():
                if isinstance(label_item.widget(), QLabel):
                    label_item.widget().setText(tr(key))
        self.set_entries(self._entries)


class BattleLogPage(InterfacePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("battleLogInterface", "page_battle_log_title", "page_battle_log_subtitle", parent)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        self.content_layout.addWidget(splitter)

        self.master_card = HeaderCardWidget(splitter)
        self.master_card.setTitle(tr("card_record_list_title"))
        splitter.addWidget(self.master_card)

        master_wrapper = QWidget(self.master_card)
        self.master_card.viewLayout.addWidget(master_wrapper)
        master_layout = QVBoxLayout(master_wrapper)
        master_layout.setContentsMargins(0, 0, 0, 0)
        master_layout.setSpacing(12)

        action_row = QWidget(master_wrapper)
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.reload_btn = PrimaryPushButton(tr("btn_refresh_records"), action_row)
        self.record_count = CaptionLabel(tr("record_count_fmt", count=0), action_row)
        action_layout.addWidget(self.reload_btn)
        action_layout.addStretch()
        action_layout.addWidget(self.record_count)
        master_layout.addWidget(action_row)

        self.record_list = ListWidget(master_wrapper)
        self.record_list.setMinimumWidth(340)
        master_layout.addWidget(self.record_list, 1)

        detail = QWidget(splitter)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(16)

        self.metrics_card = HeaderCardWidget(detail)
        self.metrics_card.setTitle(tr("card_core_metrics_title"))
        detail_layout.addWidget(self.metrics_card)
        metrics_wrapper = QWidget(self.metrics_card)
        self.metrics_card.viewLayout.addWidget(metrics_wrapper)
        metrics_grid = QGridLayout(metrics_wrapper)
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(12)

        total_tile, self.total_title_lbl, self.summary_total = self._create_metric_tile(tr("metric_total_damage"), "0.00", metrics_wrapper)
        dps_tile, self.dps_title_lbl, self.summary_dps = self._create_metric_tile(tr("metric_dps"), "0.00", metrics_wrapper)
        duration_tile, self.dur_title_lbl, self.summary_duration = self._create_metric_tile(tr("metric_duration"), format_duration(0), metrics_wrapper)
        players_tile, self.mvp_title_lbl, self.summary_players = self._create_metric_tile(tr("metric_mvp"), "-", metrics_wrapper)
        metrics_grid.addWidget(total_tile, 0, 0)
        metrics_grid.addWidget(dps_tile, 0, 1)
        metrics_grid.addWidget(duration_tile, 1, 0)
        metrics_grid.addWidget(players_tile, 1, 1)

        self.ranking_card = HeaderCardWidget(detail)
        self.ranking_card.setTitle(tr("card_damage_ranking_title"))
        detail_layout.addWidget(self.ranking_card, 1)
        ranking_wrapper = QWidget(self.ranking_card)
        self.ranking_card.viewLayout.addWidget(ranking_wrapper)
        ranking_layout = QVBoxLayout(ranking_wrapper)
        ranking_layout.setContentsMargins(12, 12, 12, 12)
        ranking_layout.setSpacing(10)
        self.table_shell = QFrame(ranking_wrapper)
        self.table_shell.setObjectName("rankingTableShell")
        table_shell_layout = QVBoxLayout(self.table_shell)
        table_shell_layout.setContentsMargins(0, 0, 0, 0)
        table_shell_layout.setSpacing(0)
        self.table = TableWidget(self.table_shell)
        self.table.setColumnCount(6)
        self._update_table_headers()
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_shell_layout.addWidget(self.table, 1)
        ranking_layout.addWidget(self.table_shell, 1)
        self._records: list[CombatRecord] = []
        self._selected_record: CombatRecord | None = None

    def _update_table_headers(self) -> None:
        self.table.setHorizontalHeaderLabels([
            tr("col_rank"),
            tr("col_character"),
            tr("col_total_damage"),
            tr("col_share"),
            tr("col_crit_rate"),
            tr("col_max_damage"),
        ])

    def _create_metric_tile(self, title: str, value: str, parent: QWidget) -> tuple[QFrame, CaptionLabel, StrongBodyLabel]:
        frame = QFrame(parent)
        frame.setObjectName("battleMetricTile")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        title_label = CaptionLabel(title, frame)
        value_label = StrongBodyLabel(value, frame)
        setFont(value_label, 22, QFont.Weight.DemiBold)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()
        return frame, title_label, value_label

    def set_records(self, records: list[CombatRecord]) -> None:
        self._records = records
        self.record_count.setText(tr("record_count_fmt", count=len(records)))
        selected_key = None
        current = self.record_list.currentItem()
        if current is not None:
            selected_key = current.data(Qt.ItemDataRole.UserRole)
        self.record_list.clear()
        for record in records:
            item_text = (
                f"{record.label}\n"
                f"{tr('record_item_summary_fmt', damage=f'{record.total_damage:.2f}', dps=f'{record.dps:.2f}', duration=format_duration(record.duration_ms))}"
            )
            self.record_list.addItem(item_text)
            item = self.record_list.item(self.record_list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, (str(record.file_path), record.record_index))
            item.setToolTip(f"{record.label}\n{record.file_path.name}")
            if item.data(Qt.ItemDataRole.UserRole) == selected_key:
                self.record_list.setCurrentItem(item)
        if self.record_list.currentItem() is None and self.record_list.count() > 0:
            self.record_list.setCurrentRow(0)

    def show_record(self, record: CombatRecord | None) -> None:
        self._selected_record = record
        if record is None:
            self.summary_total.setText("0.00")
            self.summary_dps.setText("0.00")
            self.summary_duration.setText(format_duration(0))
            self.summary_players.setText("-")
            self.table.setRowCount(0)
            return

        self.summary_total.setText(f"{record.total_damage:.2f}")
        self.summary_dps.setText(f"{record.dps:.2f}")
        self.summary_duration.setText(format_duration(record.duration_ms))
        self.summary_players.setText(
            max(record.players, key=lambda player: player.total_damage).display_name if record.players else "-"
        )
        self.table.setRowCount(len(record.players))
        for row, player in enumerate(record.players):
            percent = 0.0 if record.total_damage <= 0 else (player.total_damage / record.total_damage) * 100.0
            values = [
                str(row + 1),
                player.display_name,
                f"{player.total_damage:.2f}",
                f"{percent:.2f}%",
                f"{player.crit_rate:.2f}%",
                f"{player.max_damage:.2f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

    def retranslate_ui(self) -> None:
        self.master_card.setTitle(tr("card_record_list_title"))
        self.reload_btn.setText(tr("btn_refresh_records"))
        self.metrics_card.setTitle(tr("card_core_metrics_title"))
        self.total_title_lbl.setText(tr("metric_total_damage"))
        self.dps_title_lbl.setText(tr("metric_dps"))
        self.dur_title_lbl.setText(tr("metric_duration"))
        self.mvp_title_lbl.setText(tr("metric_mvp"))
        self.ranking_card.setTitle(tr("card_damage_ranking_title"))
        self._update_table_headers()
        self.set_records(self._records)
        self.show_record(self._selected_record)


class SettingsPage(InterfacePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("settingsInterface", "page_settings_title", "page_settings_subtitle", parent)

        # Language Card
        self.lang_card = HeaderCardWidget(tr("card_language_title"), self)
        self.content_layout.addWidget(self.lang_card)
        lang_wrapper = QWidget(self.lang_card)
        self.lang_card.viewLayout.addWidget(lang_wrapper)
        lang_form = QFormLayout(lang_wrapper)
        lang_form.setContentsMargins(0, 0, 0, 0)
        self.language_combo = ComboBox(lang_wrapper)
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("简体中文", "zh")
        self.language_hint = CaptionLabel(tr("language_hint"), lang_wrapper)
        self.lang_form_label = QLabel(tr("field_language"), lang_wrapper)
        lang_form.addRow(self.lang_form_label, self.language_combo)
        lang_form.addRow("", self.language_hint)

        # Theme Card
        self.theme_card = HeaderCardWidget(tr("card_theme_title"), self)
        self.content_layout.addWidget(self.theme_card)
        theme_wrapper = QWidget(self.theme_card)
        self.theme_card.viewLayout.addWidget(theme_wrapper)
        theme_form = QFormLayout(theme_wrapper)
        theme_form.setContentsMargins(0, 0, 0, 0)
        self.theme_combo = ComboBox(theme_wrapper)
        self._refresh_theme_combo_items()
        self.theme_hint = CaptionLabel(tr("theme_hint"), theme_wrapper)
        self.theme_form_label = QLabel(tr("field_theme_mode"), theme_wrapper)
        theme_form.addRow(self.theme_form_label, self.theme_combo)
        theme_form.addRow("", self.theme_hint)

        # Log Path Card
        self.log_card = HeaderCardWidget(tr("card_log_path_title"), self)
        self.content_layout.addWidget(self.log_card)
        log_wrapper = QWidget(self.log_card)
        self.log_card.viewLayout.addWidget(log_wrapper)
        log_form = QFormLayout(log_wrapper)
        log_form.setContentsMargins(0, 0, 0, 0)
        self.log_dir_label = CaptionLabel("-", log_wrapper)
        self.log_size_label = CaptionLabel("-", log_wrapper)
        self.log_dir_btn = PrimaryPushButton(tr("btn_select_log_dir"), log_wrapper)
        self.log_dir_refresh_btn = PushButton(tr("btn_refresh_dir_size"), log_wrapper)
        log_actions = QWidget(log_wrapper)
        log_actions_layout = QHBoxLayout(log_actions)
        log_actions_layout.setContentsMargins(0, 0, 0, 0)
        log_actions_layout.addWidget(self.log_dir_btn)
        log_actions_layout.addWidget(self.log_dir_refresh_btn)
        log_actions_layout.addStretch()
        self.log_path_form_lbl1 = QLabel(tr("field_current_path"), log_wrapper)
        self.log_path_form_lbl2 = QLabel(tr("field_dir_size"), log_wrapper)
        log_form.addRow(self.log_path_form_lbl1, self.log_dir_label)
        log_form.addRow(self.log_path_form_lbl2, self.log_size_label)
        log_form.addRow("", log_actions)

        # Hotkey Card
        self.hotkey_card = HeaderCardWidget(tr("card_hotkey_title"), self)
        self.content_layout.addWidget(self.hotkey_card)
        hotkey_wrapper = QWidget(self.hotkey_card)
        self.hotkey_card.viewLayout.addWidget(hotkey_wrapper)
        hotkey_form = QFormLayout(hotkey_wrapper)
        hotkey_form.setContentsMargins(0, 0, 0, 0)
        self.hotkey_edit = SingleHotkeyEdit(hotkey_wrapper)
        self.hotkey_hint = CaptionLabel(tr("hotkey_hint"), hotkey_wrapper)
        self.hotkey_status = CaptionLabel("-", hotkey_wrapper)
        self.hotkey_form_lbl = QLabel(tr("field_toggle_overlays_hotkey"), hotkey_wrapper)
        hotkey_form.addRow(self.hotkey_form_lbl, self.hotkey_edit)
        hotkey_form.addRow("", self.hotkey_hint)
        hotkey_form.addRow("", self.hotkey_status)

        # Combat Behavior Card
        self.battle_card = HeaderCardWidget(tr("card_combat_behavior_title"), self)
        self.content_layout.addWidget(self.battle_card)
        battle_wrapper = QWidget(self.battle_card)
        self.battle_card.viewLayout.addWidget(battle_wrapper)
        battle_form = QFormLayout(battle_wrapper)
        battle_form.setContentsMargins(0, 0, 0, 0)
        self.merge_multi_phase_switch = SwitchButton(battle_wrapper)
        self.merge_multi_phase_switch.setOnText(tr("switch_on"))
        self.merge_multi_phase_switch.setOffText(tr("switch_off"))
        self.merge_multi_phase_hint = CaptionLabel(tr("merge_multi_phase_hint"), battle_wrapper)
        self.merge_form_lbl = QLabel(tr("field_merge_multi_phase"), battle_wrapper)
        battle_form.addRow(self.merge_form_lbl, self.merge_multi_phase_switch)
        battle_form.addRow("", self.merge_multi_phase_hint)

        # About Card
        self.info_card = HeaderCardWidget(tr("card_about_title"), self)
        self.content_layout.addWidget(self.info_card)
        info_wrapper = QWidget(self.info_card)
        self.info_card.viewLayout.addWidget(info_wrapper)
        info_layout = QVBoxLayout(info_wrapper)
        info_layout.setContentsMargins(0, 0, 0, 0)
        self.app_name = CaptionLabel(tr("about_app_name"), info_wrapper)
        self.ws_port = CaptionLabel("-", info_wrapper)
        self.service_log_dir = CaptionLabel("-", info_wrapper)
        self.deps = CaptionLabel(tr("about_frontend"), info_wrapper)
        self.feedback = CaptionLabel(tr("about_version"), info_wrapper)
        self.bililink = HyperlinkLabel(QUrl("https://space.bilibili.com/605886"), "By 极黑的绅士君")
        self.groupid = CaptionLabel(tr("about_group"), info_wrapper)
        for widget in (self.app_name, self.bililink, self.groupid, self.feedback, self.ws_port, self.service_log_dir, self.deps):
            info_layout.addWidget(widget)

        self._service_config: ServiceConfig | None = None

    def _refresh_theme_combo_items(self) -> None:
        current_idx = self.theme_combo.currentIndex()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems([tr("theme_system"), tr("theme_light"), tr("theme_dark")])
        if current_idx >= 0:
            self.theme_combo.setCurrentIndex(current_idx)
        self.theme_combo.blockSignals(False)

    def set_language(self, lang: str) -> None:
        idx = 1 if str(lang).strip().lower().startswith("zh") else 0
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(idx)
        self.language_combo.blockSignals(False)

    def language(self) -> str:
        return "zh" if self.language_combo.currentIndex() == 1 else "en"

    def set_theme_mode(self, mode: str) -> None:
        index = {"system": 0, "light": 1, "dark": 2}.get(str(mode or "system").strip().lower(), 0)
        self.theme_combo.setCurrentIndex(index)

    def theme_mode(self) -> str:
        return {0: "system", 1: "light", 2: "dark"}.get(self.theme_combo.currentIndex(), "system")

    def set_hotkey(self, hotkey: str) -> None:
        self.hotkey_edit.setKeySequence(QKeySequence(hotkey or "Ctrl+O"))

    def hotkey(self) -> str:
        sequence = self.hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        return sequence or "Ctrl+O"

    def set_hotkey_status(self, message: str, is_error: bool = False) -> None:
        self.hotkey_status.setText(message)
        self.hotkey_status.setStyleSheet(f"color: {'#ff5f56' if is_error else '#32b14a'};")

    def set_merge_multi_phase_enemy_battles(self, enabled: bool) -> None:
        self.merge_multi_phase_switch.setChecked(enabled)

    def merge_multi_phase_enemy_battles(self) -> bool:
        return self.merge_multi_phase_switch.isChecked()

    def set_log_dir(self, path: Path) -> None:
        self.log_dir_label.setText(str(path))

    def set_log_size(self, size_bytes: int) -> None:
        self.log_size_label.setText(_format_directory_size(size_bytes))

    def set_service_info(self, config: ServiceConfig) -> None:
        self._service_config = config
        self.ws_port.setText(tr("about_ws_port_fmt", port=config.ws_port))
        self.service_log_dir.setText(tr("about_log_dir_fmt", dir=config.log_dir))

    def retranslate_ui(self) -> None:
        self.lang_card.setTitle(tr("card_language_title"))
        self.lang_form_label.setText(tr("field_language"))
        self.language_hint.setText(tr("language_hint"))

        self.theme_card.setTitle(tr("card_theme_title"))
        self.theme_form_label.setText(tr("field_theme_mode"))
        self._refresh_theme_combo_items()
        self.theme_hint.setText(tr("theme_hint"))

        self.log_card.setTitle(tr("card_log_path_title"))
        self.log_path_form_lbl1.setText(tr("field_current_path"))
        self.log_path_form_lbl2.setText(tr("field_dir_size"))
        self.log_dir_btn.setText(tr("btn_select_log_dir"))
        self.log_dir_refresh_btn.setText(tr("btn_refresh_dir_size"))

        self.hotkey_card.setTitle(tr("card_hotkey_title"))
        self.hotkey_form_lbl.setText(tr("field_toggle_overlays_hotkey"))
        self.hotkey_hint.setText(tr("hotkey_hint"))

        self.battle_card.setTitle(tr("card_combat_behavior_title"))
        self.merge_form_lbl.setText(tr("field_merge_multi_phase"))
        self.merge_multi_phase_switch.setOnText(tr("switch_on"))
        self.merge_multi_phase_switch.setOffText(tr("switch_off"))
        self.merge_multi_phase_hint.setText(tr("merge_multi_phase_hint"))

        self.info_card.setTitle(tr("card_about_title"))
        self.app_name.setText(tr("about_app_name"))
        self.deps.setText(tr("about_frontend"))
        self.feedback.setText(tr("about_version"))
        self.groupid.setText(tr("about_group"))
        if self._service_config is not None:
            self.set_service_info(self._service_config)


class MainWindow(FluentWindow):
    def __init__(self, app_config: AppConfig, config_path: Path) -> None:
        super().__init__()
        self.app_config = app_config
        self.config_path = config_path
        set_locale(self.app_config.language)
        self.service_controller = ServiceController(self.app_config.service)
        self.overlay_manager = OverlayManager(self.app_config.service.ws_port, on_entry_changed=self._handle_overlay_entry_changed)
        self.avatar_index = _load_avatar_index()
        self.records: list[CombatRecord] = []
        self.current_state = ServiceState.WAITING_GAME
        self.current_session_id: str | None = None
        self.current_flow: FlowKey | None = None
        self.current_metrics = RuntimeMetrics()
        self.current_squad: list[SquadMemberPayload] = []
        self._global_hotkey_registered = False
        self._registered_hotkey = ""
        self._game_dir_infobar: InfoBar | None = None
        self._restart_required_infobar: InfoBar | None = None
        self._npcap_infobar: InfoBar | None = None

        self.log_handler = QtLogHandler(self.service_controller.queue)
        self.log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(self.log_handler)

        self.home_page = HomePage(self.avatar_index, self)
        self.overlay_page = OverlayPage(self)
        self.records_page = BattleLogPage(self)
        self.settings_page = SettingsPage(self)

        self._init_window()
        self._bind_events()
        self.home_page.status_card.set_squad_members([])
        self._refresh_overlay_views()
        self._load_records()
        self._refresh_settings_page()
        self._apply_gui_theme()
        self.overlay_manager.sync_entries(self.app_config.overlays)
        self._ensure_game_directory_ready()
        self._update_service_status()

        self.queue_timer = QTimer(self)
        self.queue_timer.setInterval(150)
        self.queue_timer.timeout.connect(self._drain_queue)
        self.queue_timer.start()

    def _init_window(self) -> None:
        self.resize(1200, 800)
        self.setWindowTitle(tr("app_window_title"))
        icon_path = _app_icon_path()
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))
        self.navigationInterface.setExpandWidth(220)
        self.navigationInterface.setCollapsible(False)
        self.addSubInterface(self.home_page, FIF.HOME, tr("nav_home"))
        self.addSubInterface(self.overlay_page, FIF.APPLICATION, tr("nav_overlay"))
        self.navigationInterface.addSeparator()
        self.addSubInterface(self.records_page, FIF.HISTORY, tr("nav_battle_log"), NavigationItemPosition.SCROLL)
        self.addSubInterface(self.settings_page, FIF.SETTING, tr("nav_settings"), NavigationItemPosition.BOTTOM)

    def _bind_events(self) -> None:
        self.home_page.overlay_status_card.visibility_switch.checkedChanged.connect(self._apply_home_overlay_visibility)
        self.overlay_page.overlay_list.currentItemChanged.connect(self._sync_overlay_selection)
        self.overlay_page.add_url_btn.clicked.connect(self._add_url_overlay)
        self.overlay_page.add_file_btn.clicked.connect(self._add_file_overlay)
        self.overlay_page.remove_btn.clicked.connect(self._remove_selected_overlay)
        self.overlay_page.enable_all_btn.clicked.connect(self._enable_all_overlays)
        self.overlay_page.disable_all_btn.clicked.connect(self._disable_all_overlays)
        self.overlay_page.name_edit.editingFinished.connect(self._apply_overlay_name)
        self.overlay_page.source_value_edit.editingFinished.connect(self._apply_overlay_source_value)
        self.overlay_page.enabled_switch.checkedChanged.connect(self._apply_overlay_enabled)
        self.overlay_page.locked_switch.checkedChanged.connect(self._apply_overlay_locked)
        self.overlay_page.click_switch.checkedChanged.connect(self._apply_overlay_click_through)
        self.overlay_page.opacity_slider.valueChanged.connect(self._apply_overlay_opacity)
        self.overlay_page.scale_slider.valueChanged.connect(self._apply_overlay_scale)
        self.records_page.reload_btn.clicked.connect(self._load_records)
        self.records_page.record_list.currentItemChanged.connect(self._sync_record_selection)
        self.settings_page.language_combo.currentIndexChanged.connect(self._apply_language_mode)
        self.settings_page.theme_combo.currentIndexChanged.connect(self._apply_theme_mode)
        self.settings_page.log_dir_btn.clicked.connect(self._choose_log_dir)
        self.settings_page.log_dir_refresh_btn.clicked.connect(self._refresh_log_dir_size)
        self.settings_page.hotkey_edit.editingFinished.connect(self._apply_overlay_hotkey)
        self.settings_page.merge_multi_phase_switch.checkedChanged.connect(self._apply_merge_multi_phase_enemy_battles)
        stacked = getattr(self, "stackedWidget", None)
        if stacked is not None:
            stacked.currentChanged.connect(self._handle_current_interface_changed)

    def _drain_queue(self) -> None:
        while True:
            try:
                event_type, payload = self.service_controller.queue.get_nowait()
            except queue.Empty:
                break
            if event_type == "log":
                self.home_page.log_card.append_log(str(payload))
            elif event_type == "state":
                data = payload if isinstance(payload, dict) else {}
                self.current_state = data.get("state", ServiceState.WAITING_GAME)
                self.current_session_id = data.get("session_id")
                self.current_flow = data.get("flow")
                self._update_service_status()
            elif event_type == "metrics":
                data = payload if isinstance(payload, dict) else {}
                self.current_metrics = data.get("metrics", RuntimeMetrics())
                self.current_flow = data.get("flow")
                self._update_service_status()
            elif event_type == "event":
                self._handle_service_event(payload if isinstance(payload, dict) else {})
            elif event_type == "error":
                exc = payload if isinstance(payload, BaseException) else RuntimeError(str(payload))
                LOGGER.error("service thread crashed", exc_info=(type(exc), exc, exc.__traceback__))
                QMessageBox.critical(self, tr("dialog_service_crashed_title"), "".join(traceback.format_exception(exc)).strip())
            elif event_type == "stopped":
                self._update_service_status()

    def _handle_service_event(self, event: dict[str, object]) -> None:
        if str(event.get("type", "")) != "SC_SELF_SCENE_INFO":
            return
        members: list[SquadMemberPayload] = []
        for item in event.get("char_list", []):
            if not isinstance(item, dict):
                continue
            battle_inst_id = item.get("battle_inst_id")
            if battle_inst_id is None:
                continue
            members.append(
                SquadMemberPayload(
                    battle_inst_id=int(battle_inst_id),
                    templateid=str(item.get("templateid")) if item.get("templateid") is not None else None,
                    display_name=str(item.get("display_name")) if item.get("display_name") is not None else None,
                    is_leader=bool(item.get("is_leader", False)),
                    squad_index=int(item.get("squad_index", len(members))),
                )
            )
        self.current_squad = members
        self.home_page.status_card.set_squad_members(self.current_squad)

    def _update_service_status(self) -> None:
        program = tr("status_running") if self.service_controller.is_running() else tr("status_stopped_restart")
        if self.current_state == ServiceState.WAITING_RESTART:
            game = tr("status_game_running_restart")
            server = tr("status_waiting_session")
        elif self.current_state == ServiceState.WAITING_CONNECTION:
            game = tr("status_game_detected")
            server = tr("status_waiting_connect")
        elif self.current_state == ServiceState.WAITING_HANDSHAKE:
            game = tr("status_game_detected")
            server = tr("status_waiting_handshake")
        elif self.current_state == ServiceState.LIVE:
            game = tr("status_game_detected")
            server = tr("status_connected_battle")
        else:
            game = tr("status_waiting_game")
            server = tr("status_disconnected")
        flow = (
            self.current_session_id
            if self.current_flow is None
            else f"{self.current_flow.client.ip}:{self.current_flow.client.port} -> {self.current_flow.server.ip}:{self.current_flow.server.port}"
        )
        self.home_page.status_card.set_status(program, game, server, flow or "-")
        self.home_page.overlay_status_card.set_entries(self.app_config.overlays)
        self.home_page.overlay_status_card.set_all_visible(all(entry.enabled for entry in self.app_config.overlays))
        self.settings_page.set_service_info(self.app_config.service)
        self._sync_restart_required_infobar()

    def _refresh_overlay_views(self) -> None:
        self.overlay_page.set_entries(self.app_config.overlays)
        self._sync_overlay_selection()
        self._update_service_status()

    def _selected_overlay(self) -> OverlayEntry | None:
        entry_id = self.overlay_page.selected_entry_id()
        if entry_id is None:
            return None
        for entry in self.app_config.overlays:
            if entry.id == entry_id:
                return entry
        return None

    def _sync_overlay_selection(self) -> None:
        self.overlay_page.show_entry(self._selected_overlay())

    def _replace_overlay_entry(self, updated: OverlayEntry) -> None:
        self.app_config.overlays = [updated if entry.id == updated.id else entry for entry in self.app_config.overlays]
        self.overlay_manager.apply_entry(updated)
        save_app_config(self.app_config, self.config_path)
        self._refresh_overlay_views()

    def _handle_overlay_entry_changed(self, entry: OverlayEntry) -> None:
        self.app_config.overlays = [entry if item.id == entry.id else item for item in self.app_config.overlays]
        save_app_config(self.app_config, self.config_path)
        self._refresh_overlay_views()

    def _add_url_overlay(self) -> None:
        url, ok = QInputDialog.getText(self, tr("dialog_add_url_title"), tr("dialog_add_url_prompt"))
        if not ok or not url.strip():
            return
        entry = OverlayEntry(
            id=str(uuid.uuid4()),
            name=tr("overlay_name_online_default"),
            source_type=OverlaySourceType.URL,
            source_value=url.strip(),
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
        )
        self.app_config.overlays.append(entry)
        save_app_config(self.app_config, self.config_path)
        self.overlay_manager.apply_entry(entry)
        self._refresh_overlay_views()

    def _add_file_overlay(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("dialog_select_html_title"), str(ROOT), "HTML Files (*.html)")
        if not path:
            return
        entry = OverlayEntry(
            id=str(uuid.uuid4()),
            name=Path(path).stem,
            source_type=OverlaySourceType.FILE,
            source_value=path,
            enabled=True,
            locked=False,
            click_through=False,
            opacity=1.0,
            scale=1.0,
        )
        self.app_config.overlays.append(entry)
        save_app_config(self.app_config, self.config_path)
        self.overlay_manager.apply_entry(entry)
        self._refresh_overlay_views()

    def _remove_selected_overlay(self) -> None:
        entry = self._selected_overlay()
        if entry is None or entry.source_type == OverlaySourceType.BUILTIN:
            return
        self.app_config.overlays = [item for item in self.app_config.overlays if item.id != entry.id]
        self.overlay_manager.remove_entry(entry.id)
        save_app_config(self.app_config, self.config_path)
        self._refresh_overlay_views()

    def _enable_all_overlays(self) -> None:
        self.app_config.overlays = [replace(entry, enabled=True) for entry in self.app_config.overlays]
        save_app_config(self.app_config, self.config_path)
        self.overlay_manager.set_enabled_entries_visible(True)
        self.overlay_manager.sync_entries(self.app_config.overlays)
        self._refresh_overlay_views()

    def _disable_all_overlays(self) -> None:
        self.app_config.overlays = [replace(entry, enabled=False) for entry in self.app_config.overlays]
        save_app_config(self.app_config, self.config_path)
        self.overlay_manager.set_enabled_entries_visible(False)
        self.overlay_manager.sync_entries(self.app_config.overlays)
        self._refresh_overlay_views()

    def _apply_overlay_name(self) -> None:
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is None:
            return
        name = self.overlay_page.name_edit.text().strip() or entry.name
        if name != entry.name:
            self._replace_overlay_entry(replace(entry, name=name))

    def _apply_overlay_source_value(self) -> None:
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is None or entry.source_type != OverlaySourceType.URL:
            return
        value = self.overlay_page.source_value_edit.text().strip()
        if value and value != entry.source_value:
            self._replace_overlay_entry(replace(entry, source_value=value))

    def _apply_overlay_enabled(self, checked: bool) -> None:
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is not None and checked != entry.enabled:
            self._replace_overlay_entry(replace(entry, enabled=checked))

    def _apply_overlay_locked(self, checked: bool) -> None:
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is not None and checked != entry.locked:
            self._replace_overlay_entry(replace(entry, locked=checked))

    def _apply_overlay_click_through(self, checked: bool) -> None:
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is not None and checked != entry.click_through:
            self._replace_overlay_entry(replace(entry, click_through=checked))

    def _apply_overlay_opacity(self, value: int) -> None:
        self.overlay_page.opacity_value.setText(f"{value}%")
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is None:
            return
        opacity = max(0.1, min(1.0, value / 100.0))
        if abs(opacity - entry.opacity) > 0.0001:
            self._replace_overlay_entry(replace(entry, opacity=opacity))

    def _apply_overlay_scale(self, value: int) -> None:
        self.overlay_page.scale_value.setText(f"{value}%")
        if self.overlay_page._updating:
            return
        entry = self._selected_overlay()
        if entry is None:
            return
        scale = max(0.5, min(3.0, value / 100.0))
        if abs(scale - entry.scale) <= 0.0001:
            return
        geometry = entry.geometry
        scaled_geometry = geometry
        if geometry is not None and entry.scale > 0:
            ratio = scale / entry.scale
            scaled_geometry = OverlayGeometry(
                x=geometry.x,
                y=geometry.y,
                width=max(1, int(round(geometry.width * ratio))),
                height=max(1, int(round(geometry.height * ratio))),
            )
        self._replace_overlay_entry(replace(entry, scale=scale, geometry=scaled_geometry))

    def _load_records(self) -> None:
        resolved_log_dir = _resolve_log_dir(self.app_config.service.log_dir)
        if resolved_log_dir != self.app_config.service.log_dir:
            self.app_config.service.log_dir = resolved_log_dir
            save_app_config(self.app_config, self.config_path)
            self._refresh_settings_page()
        self.records = load_combat_records(resolved_log_dir)
        self.records_page.set_records(self.records)
        self._sync_record_selection()

    def _sync_record_selection(self) -> None:
        selected = None
        item = self.records_page.record_list.currentItem()
        if item is not None:
            key = item.data(Qt.ItemDataRole.UserRole)
            for record in self.records:
                if (str(record.file_path), record.record_index) == key:
                    selected = record
                    break
        self.records_page.show_record(selected)

    def _handle_current_interface_changed(self, index: int) -> None:
        stacked = getattr(self, "stackedWidget", None)
        if stacked is None:
            return
        if stacked.widget(index) is self.records_page:
            self._load_records()

    def _refresh_settings_page(self) -> None:
        self.settings_page.language_combo.blockSignals(True)
        self.settings_page.theme_combo.blockSignals(True)
        self.settings_page.hotkey_edit.blockSignals(True)
        self.settings_page.merge_multi_phase_switch.blockSignals(True)
        self.settings_page.set_language(self.app_config.language)
        self.settings_page.set_theme_mode(self.app_config.theme_mode)
        self.settings_page.set_hotkey(self.app_config.toggle_overlays_hotkey)
        self.settings_page.set_merge_multi_phase_enemy_battles(self.app_config.service.merge_multi_phase_enemy_battles)
        self.settings_page.language_combo.blockSignals(False)
        self.settings_page.theme_combo.blockSignals(False)
        self.settings_page.hotkey_edit.blockSignals(False)
        self.settings_page.merge_multi_phase_switch.blockSignals(False)
        self.settings_page.set_log_dir(self.app_config.service.log_dir)
        self.settings_page.set_service_info(self.app_config.service)
        self._refresh_log_dir_size()
        self._update_overlay_shortcut()

    def _refresh_log_dir_size(self) -> None:
        self.settings_page.set_log_size(_directory_size(self.app_config.service.log_dir))

    def _apply_merge_multi_phase_enemy_battles(self, checked: bool) -> None:
        if checked == self.app_config.service.merge_multi_phase_enemy_battles:
            return
        self.app_config.service.merge_multi_phase_enemy_battles = checked
        service = getattr(self.service_controller, "_service", None)
        active_session = getattr(service, "active_session", None) if service is not None else None
        if active_session is not None:
            active_session.merge_multi_phase_enemy_battles = checked
        save_app_config(self.app_config, self.config_path)

    def _choose_log_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, tr("dialog_select_log_dir_title"), str(self.app_config.service.log_dir))
        if not selected:
            return
        target = Path(selected).resolve()
        self.app_config.service.log_dir = target
        save_app_config(self.app_config, self.config_path)
        self._refresh_settings_page()
        self._load_records()

    def _start_service_if_needed(self) -> None:
        if not self._ensure_npcap_ready():
            self._update_service_status()
            return
        if not self.service_controller.is_running():
            self.service_controller.start()
        self._update_service_status()

    def _clear_game_dir_infobar(self) -> None:
        if self._game_dir_infobar is None:
            return
        self._game_dir_infobar.close()
        self._game_dir_infobar = None

    def _clear_restart_required_infobar(self) -> None:
        if self._restart_required_infobar is None:
            return
        self._restart_required_infobar.close()
        self._restart_required_infobar = None

    def _clear_npcap_infobar(self) -> None:
        if self._npcap_infobar is None:
            return
        self._npcap_infobar.close()
        self._npcap_infobar = None

    def _show_game_dir_infobar(self) -> None:
        if self._game_dir_infobar is not None:
            return
        bar = InfoBar.error(
            title=tr("infobar_error_title"),
            content=tr("infobar_game_dir_missing"),
            duration=-1,
            position=InfoBarPosition.TOP,
            parent=self,
        )
        button = PrimaryPushButton(tr("btn_choose_dir"), bar)
        button.clicked.connect(self._choose_game_dir)
        bar.addWidget(button)
        self._game_dir_infobar = bar

    def _show_restart_required_infobar(self) -> None:
        if self._restart_required_infobar is not None:
            return
        self._restart_required_infobar = InfoBar.error(
            title=tr("infobar_notice_title"),
            content=tr("infobar_restart_game_notice"),
            duration=-1,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _show_npcap_infobar(self) -> None:
        if self._npcap_infobar is not None:
            return
        self._npcap_infobar = InfoBar.error(
            title=tr("infobar_error_title"),
            content=tr("infobar_npcap_missing"),
            duration=-1,
            position=InfoBarPosition.TOP,
            parent=self,
        )

    def _sync_restart_required_infobar(self) -> None:
        if self.current_state == ServiceState.WAITING_RESTART:
            self._show_restart_required_infobar()
            return
        self._clear_restart_required_infobar()

    def _ensure_npcap_ready(self) -> bool:
        if has_npcap():
            self._clear_npcap_infobar()
            return True
        self._show_npcap_infobar()
        return False

    def _choose_game_dir(self) -> None:
        start_dir = str(self.app_config.service.dll_dir) if self.app_config.service.dll_dir else str(ROOT)
        selected = QFileDialog.getExistingDirectory(self, tr("dialog_choose_dir_title"), start_dir)
        if not selected:
            return
        target = Path(selected).resolve()
        if not _is_valid_game_dir(target):
            QMessageBox.warning(self, tr("msg_invalid_game_dir_title"), tr("msg_invalid_game_dir_body"))
            self._show_game_dir_infobar()
            return
        self.app_config.service.dll_dir = target
        self.app_config.service.game_exe = "Endfield.exe"
        save_app_config(self.app_config, self.config_path)
        self._clear_game_dir_infobar()
        self._refresh_settings_page()
        self._start_service_if_needed()

    def _ensure_game_directory_ready(self) -> None:
        if not self._ensure_npcap_ready():
            self._update_service_status()
            return
        if _is_valid_game_dir(self.app_config.service.dll_dir):
            self._clear_game_dir_infobar()
            self._start_service_if_needed()
            return
        self._show_game_dir_infobar()
        self._update_service_status()

    def _apply_language_mode(self, *_args) -> None:
        new_lang = self.settings_page.language()
        if new_lang != self.app_config.language:
            self.app_config.language = new_lang
            save_app_config(self.app_config, self.config_path)
        set_locale(new_lang)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("app_window_title"))
        nav_mapping = [
            (self.home_page, tr("nav_home")),
            (self.overlay_page, tr("nav_overlay")),
            (self.records_page, tr("nav_battle_log")),
            (self.settings_page, tr("nav_settings")),
        ]
        for page, nav_title in nav_mapping:
            item = self.navigationInterface.widget(page.objectName())
            if item is not None and hasattr(item, "setText"):
                item.setText(nav_title)

        self.home_page.retranslate_ui()
        self.overlay_page.retranslate_ui()
        self.records_page.retranslate_ui()
        self.settings_page.retranslate_ui()
        self._update_service_status()
        self._update_overlay_shortcut()

    def _apply_theme_mode(self, *_args) -> None:
        mode = self.settings_page.theme_mode()
        if mode != self.app_config.theme_mode:
            self.app_config.theme_mode = mode
            save_app_config(self.app_config, self.config_path)
        self._apply_gui_theme(mode)

    def _apply_overlay_hotkey(self, *_args) -> None:
        hotkey = self.settings_page.hotkey()
        if self._update_overlay_shortcut(hotkey):
            if hotkey != self.app_config.toggle_overlays_hotkey:
                self.app_config.toggle_overlays_hotkey = hotkey
                save_app_config(self.app_config, self.config_path)
            self.settings_page.hotkey_edit.blockSignals(True)
            self.settings_page.set_hotkey(self.app_config.toggle_overlays_hotkey)
            self.settings_page.hotkey_edit.blockSignals(False)
            return
        self.settings_page.hotkey_edit.blockSignals(True)
        self.settings_page.set_hotkey(self.app_config.toggle_overlays_hotkey)
        self.settings_page.hotkey_edit.blockSignals(False)

    def _update_overlay_shortcut(self, hotkey: str | None = None) -> bool:
        target_hotkey = hotkey or self.app_config.toggle_overlays_hotkey or "Ctrl+O"
        if sys.platform != "win32" or USER32 is None:
            self.settings_page.set_hotkey_status(tr("hotkey_not_supported"), is_error=True)
            return False
        native = _portable_hotkey_to_native(target_hotkey)
        if native is None:
            self.settings_page.set_hotkey_status(tr("hotkey_invalid_format"), is_error=True)
            return False
        hwnd = int(self.winId())
        previous_hotkey = self._registered_hotkey
        if self._global_hotkey_registered:
            USER32.UnregisterHotKey(hwnd, GLOBAL_HOTKEY_ID)
            self._global_hotkey_registered = False
        modifiers, vk = native
        if USER32.RegisterHotKey(hwnd, GLOBAL_HOTKEY_ID, modifiers | MOD_NOREPEAT, vk):
            self._global_hotkey_registered = True
            self._registered_hotkey = target_hotkey
            self.settings_page.set_hotkey_status(tr("hotkey_success_fmt", hotkey=target_hotkey))
            return True
        if previous_hotkey:
            previous_native = _portable_hotkey_to_native(previous_hotkey)
            if previous_native is not None:
                prev_modifiers, prev_vk = previous_native
                if USER32.RegisterHotKey(hwnd, GLOBAL_HOTKEY_ID, prev_modifiers | MOD_NOREPEAT, prev_vk):
                    self._global_hotkey_registered = True
                    self._registered_hotkey = previous_hotkey
        self.settings_page.set_hotkey_status(tr("hotkey_conflict_fmt", hotkey=target_hotkey), is_error=True)
        return False

    def _unregister_overlay_hotkey(self) -> None:
        if sys.platform != "win32" or USER32 is None or not self._global_hotkey_registered:
            return
        USER32.UnregisterHotKey(int(self.winId()), GLOBAL_HOTKEY_ID)
        self._global_hotkey_registered = False

    def _toggle_overlay_visibility(self) -> None:
        self.overlay_manager.set_enabled_entries_visible(not self.overlay_manager.enabled_entries_visible())

    def _apply_home_overlay_visibility(self, checked: bool) -> None:
        if checked:
            self._enable_all_overlays()
        else:
            self._disable_all_overlays()

    def _apply_gui_theme(self, mode: str | None = None) -> None:
        setTheme(_theme_from_mode(mode or self.app_config.theme_mode))
        self.setCustomBackgroundColor("#f3f3f3", "#202020")
        dark = isDarkTheme()
        page_qss = "background: transparent;"
        label_color = "#f5f5f5" if dark else "#202020"
        subtle_label_color = "#d0d0d0" if dark else "#606060"
        text_edit_qss = (
            "QPlainTextEdit { background: rgba(18, 18, 18, 0.94); color: #f5f5f5; border-radius: 8px; }"
            if dark
            else "QPlainTextEdit { background: rgba(255, 255, 255, 0.94); color: #202020; border-radius: 8px; }"
        )
        table_qss = (
            "QTableView { background: transparent; color: #f5f5f5; gridline-color: rgba(255,255,255,0.08); "
            "border: none; border-radius: 12px; selection-background-color: rgba(255,255,255,0.12); selection-color: #ffffff; } "
            "QHeaderView { background: transparent; } "
            "QHeaderView::section { background: rgba(42, 42, 42, 0.96); color: #f5f5f5; border: none; "
            "border-bottom: 1px solid rgba(255,255,255,0.08); padding: 6px 8px; } "
            "QHeaderView::section:first { border-top-left-radius: 12px; } "
            "QHeaderView::section:last { border-top-right-radius: 12px; } "
            "QTableCornerButton::section { background: rgba(42, 42, 42, 0.96); border: none; border-top-left-radius: 12px; }"
            if dark
            else "QTableView { background: transparent; color: #202020; gridline-color: rgba(0,0,0,0.08); "
            "border: none; border-radius: 12px; selection-background-color: rgba(0,0,0,0.08); selection-color: #202020; } "
            "QHeaderView { background: transparent; } "
            "QHeaderView::section { background: rgba(245, 245, 245, 0.96); color: #202020; border: none; "
            "border-bottom: 1px solid rgba(0,0,0,0.08); padding: 6px 8px; } "
            "QHeaderView::section:first { border-top-left-radius: 12px; } "
            "QHeaderView::section:last { border-top-right-radius: 12px; } "
            "QTableCornerButton::section { background: rgba(245, 245, 245, 0.96); border: none; border-top-left-radius: 12px; }"
        )
        table_shell_qss = (
            "QFrame#rankingTableShell { background: rgba(28, 28, 28, 0.92); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; }"
            if dark
            else "QFrame#rankingTableShell { background: rgba(255, 255, 255, 0.92); border: 1px solid rgba(0,0,0,0.06); border-radius: 12px; }"
        )
        form_page_qss = (
            "QLabel { color: #f5f5f5; } "
            "QCheckBox { color: #f5f5f5; } "
            "QLineEdit, QComboBox, QKeySequenceEdit { color: #f5f5f5; background: rgba(28, 28, 28, 0.92); border-radius: 6px; }"
            if dark
            else "QLabel { color: #202020; } "
            "QCheckBox { color: #202020; } "
            "QLineEdit, QComboBox, QKeySequenceEdit { color: #202020; background: rgba(255, 255, 255, 0.92); border-radius: 6px; }"
        )
        metric_tile_qss = (
            "QFrame#battleMetricTile { background: rgba(34, 34, 34, 0.94); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; }"
            if dark
            else "QFrame#battleMetricTile { background: rgba(255, 255, 255, 0.82); border: 1px solid rgba(0, 0, 0, 0.06); border-radius: 12px; }"
        )
        for page in (self.home_page, self.overlay_page, self.records_page, self.settings_page):
            page.viewport().setStyleSheet(page_qss)
            page.container.setStyleSheet(page_qss)
            page.setStyleSheet(page_qss)
        self.overlay_page.container.setStyleSheet(form_page_qss)
        self.settings_page.container.setStyleSheet(form_page_qss)
        self.records_page.container.setStyleSheet(
            f"QLabel {{ color: {label_color}; }} "
            f"QTableView {{ color: {label_color}; }} "
            f"QHeaderView::section {{ color: {label_color}; }} "
            f"QLabel[description='true'] {{ color: {subtle_label_color}; }}"
        )
        self.home_page.log_card.log_view.setStyleSheet(text_edit_qss)
        self.records_page.table.setStyleSheet(table_qss)
        self.records_page.table_shell.setStyleSheet(table_shell_qss)
        for tile in self.records_page.findChildren(QFrame, "battleMetricTile"):
            tile.setStyleSheet(metric_tile_qss)
        self.home_page.update()
        self.overlay_page.update()
        self.records_page.update()
        self.settings_page.update()
        self.update()

    def nativeEvent(self, eventType, message):  # noqa: N802
        if sys.platform == "win32" and USER32 is not None:
            event_type = bytes(eventType).decode(errors="ignore")
            if event_type in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and int(msg.wParam) == GLOBAL_HOTKEY_ID:
                    self._toggle_overlay_visibility()
                    return True, 0
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.queue_timer.stop()
        logging.getLogger().removeHandler(self.log_handler)
        self._unregister_overlay_hotkey()
        save_app_config(self.app_config, self.config_path)
        self.overlay_manager.close_all()
        self.service_controller.stop()
        self.service_controller.join(timeout=5.0)
        super().closeEvent(event)


def run_gui(
    config_path: Path | None = None,
    debug_enabled: bool = False,
    debug_dir: Path | None = None,
) -> int:
    target_path = config_path or default_config_path()
    app_config = load_app_config(target_path)
    set_locale(app_config.language)
    app_config.service.debug_enabled = debug_enabled
    if debug_dir is not None:
        app_config.service.debug_dir = debug_dir.resolve()
    configure_logging(app_config.service.log_level)

    app = QApplication.instance() or QApplication([])
    app.setApplicationName(tr("app_title"))
    icon_path = _app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass
    app.setFont(QFont("Microsoft YaHei UI", 10))
    setTheme(_theme_from_mode(app_config.theme_mode))

    if not _is_valid_game_dir(app_config.service.dll_dir):
        if not _run_game_directory_wizard(app_config, target_path):
            return 1

    window = MainWindow(app_config, target_path)
    window.show()
    return app.exec()
