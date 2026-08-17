from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.ui.i18n import tr
from app.ui.theme import WORKFLOW_STYLE, install_shadow, set_message_label, set_pointing_hand


class TraceImportView(QWidget):
    choose_file_requested = Signal()
    parse_requested = Signal()
    logout_requested = Signal()
    file_dropped = Signal(str)
    resume_monitoring_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._selected_file_name: str | None = None
        self._parse_enabled = False
        self.setAcceptDrops(True)
        self.setObjectName("traceImportRoot")
        self.setStyleSheet(WORKFLOW_STYLE)

        outer = QVBoxLayout()
        outer.setContentsMargins(34, 30, 34, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("workflowCard")
        card.setMinimumWidth(760)
        card.setMaximumWidth(980)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 22)
        card_layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("heroStrip")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(8)

        eyebrow = QLabel(tr("import_eyebrow"))
        eyebrow.setObjectName("workflowEyebrow")
        title = QLabel(tr("import_title"))
        title.setObjectName("workflowTitle")
        title.setWordWrap(True)
        description = QLabel(tr("import_body"))
        description.setObjectName("workflowBody")
        description.setWordWrap(True)
        header_layout.addWidget(eyebrow)
        header_layout.addWidget(title)
        header_layout.addWidget(description)

        drop_zone = QFrame()
        drop_zone.setObjectName("dropZone")
        drop_layout = QHBoxLayout(drop_zone)
        drop_layout.setContentsMargins(20, 18, 20, 18)
        drop_layout.setSpacing(18)

        badge = QLabel("LOG")
        badge.setObjectName("logBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumSize(80, 64)

        file_column = QVBoxLayout()
        file_column.setSpacing(6)
        file_column_title = QLabel(tr("import_file_section"))
        file_column_title.setObjectName("sectionTitle")
        self.file_label = QLabel(tr("import_no_file"))
        self.file_label.setObjectName("fileLabel")
        self.file_label.setWordWrap(True)
        self.integrity_label = QLabel("")
        self.integrity_label.setObjectName("integrityLabel")
        self.integrity_label.setWordWrap(True)
        drop_hint = QLabel(tr("import_drop_hint"))
        drop_hint.setObjectName("dropHint")
        drop_hint.setWordWrap(True)
        file_column.addWidget(file_column_title)
        file_column.addWidget(self.file_label)
        file_column.addWidget(self.integrity_label)
        file_column.addWidget(drop_hint)
        drop_layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        drop_layout.addLayout(file_column, 1)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("progressPanel")
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(18, 14, 18, 14)
        progress_layout.setSpacing(8)
        progress_title = QLabel(tr("import_progress_title"))
        progress_title.setObjectName("sectionTitle")
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("progressLabel")
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.progress_panel.hide()
        self.message_label = QLabel("")
        self.message_label.setObjectName("messageLabel")
        self.message_label.setWordWrap(True)
        self.message_label.hide()
        progress_layout.addWidget(progress_title)
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)

        self.choose_button = QPushButton(tr("import_btn_choose"))
        self.parse_button = QPushButton(tr("import_btn_parse"))
        self.resume_monitoring_button = QPushButton(tr("import_btn_resume_monitor"))
        self.resume_monitoring_button.hide()
        self.logout_button = QPushButton(tr("logout"))
        self.parse_button.setEnabled(False)
        for button in [self.choose_button, self.parse_button]:
            button.setObjectName("primaryAction")
            button.setMinimumHeight(44)
            set_pointing_hand(button)
        self.logout_button.setObjectName("ghostAction")
        set_pointing_hand(self.logout_button)

        self.choose_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.parse_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.logout_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)
        )

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(12)
        primary_actions.addWidget(self.choose_button)
        primary_actions.addWidget(self.parse_button)

        self.resume_monitoring_button.setObjectName("secondaryAction")
        self.resume_monitoring_button.setMinimumHeight(40)
        self.resume_monitoring_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        set_pointing_hand(self.resume_monitoring_button)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(8)
        secondary_actions.addWidget(self.resume_monitoring_button)
        secondary_actions.addStretch(1)
        secondary_actions.addWidget(self.logout_button)

        card_layout.addWidget(header)
        card_layout.addWidget(drop_zone)
        card_layout.addWidget(self.progress_panel)
        card_layout.addLayout(primary_actions)
        card_layout.addLayout(secondary_actions)
        card_layout.addWidget(self.message_label)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        self.setLayout(outer)
        install_shadow(card, blur_radius=46)

        self.choose_button.clicked.connect(lambda: self.choose_file_requested.emit())
        self.parse_button.clicked.connect(lambda: self.parse_requested.emit())
        self.resume_monitoring_button.clicked.connect(lambda: self.resume_monitoring_requested.emit())
        self.logout_button.clicked.connect(lambda: self.logout_requested.emit())

    def set_resume_monitoring_available(self, available: bool) -> None:
        self.resume_monitoring_button.setVisible(available)

    @staticmethod
    def extract_log_file_path(mime_data: QMimeData) -> str | None:
        for url in mime_data.urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if local_path.lower().endswith(".log"):
                    return local_path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if self.extract_log_file_path(event.mimeData()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        local_path = self.extract_log_file_path(event.mimeData())
        if not local_path:
            event.ignore()
            return
        event.acceptProposedAction()
        self.file_dropped.emit(local_path)

    def set_selected_file(self, file_name: str | None, integrity_label: str | None = None) -> None:
        self._selected_file_name = file_name
        self._parse_enabled = bool(file_name)
        self.file_label.setText(tr("import_current_file", file=file_name) if file_name else tr("import_no_file"))
        self.integrity_label.setText(integrity_label or "")
        self._sync_parse_button()

    def set_parse_allowed(self, allowed: bool) -> None:
        self._parse_enabled = allowed and self._selected_file_name is not None
        self._sync_parse_button()

    def set_progress(self, message: str, *, current: int | None = None, total: int | None = None) -> None:
        self.progress_label.setText(message)
        self.progress_panel.show()
        self.progress_bar.show()
        if total and total > 0 and current is not None:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(current, total)))
            return
        self.progress_bar.setRange(0, 0)

    def clear_progress(self) -> None:
        self.progress_label.clear()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.progress_panel.hide()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.choose_button.setEnabled(not busy)
        self.logout_button.setEnabled(not busy)
        self._sync_parse_button()

    def set_message(self, message: str, *, error: bool = False) -> None:
        set_message_label(self.message_label, message, error=error)

    def _sync_parse_button(self) -> None:
        self.parse_button.setEnabled(not self._busy and self._selected_file_name is not None and self._parse_enabled)
