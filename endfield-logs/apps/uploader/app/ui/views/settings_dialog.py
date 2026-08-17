from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.services.settings_store import UploaderSettings
from app.ui.i18n import tr


class SettingsDialog(QDialog):
    def __init__(self, settings: UploaderSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.resize(520, 260)
        self.last_log_dir = settings.last_log_dir

        layout = QVBoxLayout()

        intro = QLabel(tr("settings_intro"))
        intro.setWordWrap(True)

        form = QFormLayout()
        defaults = UploaderSettings()
        self.api_base_url_input = QLineEdit(settings.api_base_url)
        self.web_base_url_input = QLineEdit(settings.web_base_url)
        self.api_base_url_input.setPlaceholderText(defaults.api_base_url)
        self.web_base_url_input.setPlaceholderText(defaults.web_base_url)

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("简体中文", "zh")
        current_idx = 1 if settings.language == "zh" else 0
        self.language_combo.setCurrentIndex(current_idx)

        form.addRow(tr("settings_api_url"), self.api_base_url_input)
        form.addRow(tr("settings_web_url"), self.web_base_url_input)
        form.addRow(tr("settings_language"), self.language_combo)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)

        self.reset_button = QPushButton(tr("reset_defaults"))
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)

        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.message_label)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

        self.reset_button.clicked.connect(self._reset_defaults)
        self.button_box.accepted.connect(self._accept_if_valid)
        self.button_box.rejected.connect(self.reject)

    def _reset_defaults(self) -> None:
        defaults = UploaderSettings()
        self.api_base_url_input.setText(defaults.api_base_url)
        self.web_base_url_input.setText(defaults.web_base_url)
        self.language_combo.setCurrentIndex(0)
        self.set_message(tr("settings_reset_done"))

    def _accept_if_valid(self) -> None:
        settings = self.current_settings()
        if not settings.api_base_url.startswith(("http://", "https://")):
            self.set_message(tr("settings_url_invalid"), error=True)
            return
        if not settings.web_base_url.startswith(("http://", "https://")):
            self.set_message(tr("settings_url_invalid"), error=True)
            return
        self.accept()

    def current_settings(self) -> UploaderSettings:
        return UploaderSettings(
            api_base_url=self.api_base_url_input.text().strip(),
            web_base_url=self.web_base_url_input.text().strip(),
            last_log_dir=self.last_log_dir,
            language=self.language_combo.currentData() or "en",
        )

    def set_message(self, message: str, *, error: bool = False) -> None:
        color = "#c0392b" if error else "#2c3e50"
        self.message_label.setStyleSheet(f"color: {color};")
        self.message_label.setText(message)
