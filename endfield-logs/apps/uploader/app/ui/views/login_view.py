from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.assets import asset_path
from app.ui.i18n import tr


AuthMode = Literal["login", "register"]


class LoginView(QWidget):
    login_requested = Signal(str, str)
    register_requested = Signal(str, str, str, str)
    send_register_code_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._mode: AuthMode = "login"
        self._profile_setup_token: str | None = None
        self._send_code_remaining = 0
        self._send_code_timer = QTimer(self)
        self._send_code_timer.setInterval(1000)
        self._send_code_timer.timeout.connect(self._tick_send_code_cooldown)

        self.setObjectName("loginRoot")
        self.setStyleSheet(
            """
            QWidget#loginRoot {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #f3f8ff,
                    stop: 0.45 #e6f1ff,
                    stop: 1 #eef6f0
                );
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
            }
            QScrollArea#authScroll {
                background: transparent;
                border: 0;
            }
            QScrollArea#authScroll > QWidget > QWidget {
                background: transparent;
            }
            QScrollArea#authScroll QScrollBar:vertical {
                background: transparent;
                margin: 18px 0 18px 6px;
                width: 8px;
            }
            QScrollArea#authScroll QScrollBar::handle:vertical {
                background: #c1cfde;
                border-radius: 4px;
                min-height: 36px;
            }
            QScrollArea#authScroll QScrollBar::add-line:vertical,
            QScrollArea#authScroll QScrollBar::sub-line:vertical {
                height: 0;
            }
            QFrame#heroPanel {
                background: rgba(12, 39, 72, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 28px;
            }
            QFrame#authCard {
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(18, 63, 109, 0.10);
                border-radius: 28px;
            }
            QLabel#eyebrowLabel {
                color: #9dc7ff;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#brandLogo {
                background: transparent;
            }
            QLabel#heroTitle {
                color: #f8fbff;
                font-size: 30px;
                font-weight: 700;
            }
            QLabel#heroBody {
                color: rgba(240, 246, 255, 0.78);
                font-size: 14px;
                line-height: 1.4;
            }
            QFrame#featurePill {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 18px;
            }
            QLabel#featureTitle {
                color: #ffffff;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#featureText {
                color: rgba(240, 246, 255, 0.72);
                font-size: 12px;
            }
            QLabel#cardEyebrow {
                color: #4d78aa;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            QLabel#cardTitle {
                color: #14263a;
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#cardBody {
                color: #59708a;
                font-size: 13px;
            }
            QPushButton#modeButton {
                background: transparent;
                border: 1px solid rgba(30, 75, 122, 0.10);
                border-radius: 16px;
                color: #47627f;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 14px;
            }
            QPushButton#modeButton:checked {
                background: #153d66;
                border-color: #153d66;
                color: #ffffff;
            }
            QLabel#fieldLabel {
                color: #28435f;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit {
                background: #f8fbfe;
                border: 1px solid #d7e2ef;
                border-radius: 14px;
                color: #17314b;
                font-size: 14px;
                padding: 12px 14px;
                selection-background-color: #c7defe;
            }
            QLineEdit:focus {
                border: 1px solid #3b82c4;
                background: #ffffff;
            }
            QPushButton#primaryAction {
                background: #153d66;
                border: 0;
                border-radius: 16px;
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
                padding: 14px 18px;
            }
            QPushButton#primaryAction:disabled {
                background: #b4c2d2;
                color: #eef3f9;
            }
            QPushButton#secondaryAction {
                background: transparent;
                border: 1px solid #d3dde8;
                border-radius: 16px;
                color: #35516f;
                font-size: 13px;
                font-weight: 600;
                padding: 12px 18px;
            }
            QPushButton#switchModeLink {
                background: transparent;
                border: 0;
                color: #215e9d;
                font-size: 13px;
                font-weight: 600;
                padding: 0;
                text-align: left;
            }
            QLabel#inlineHint {
                color: #6d8298;
                font-size: 12px;
            }
            QLabel#messageLabel {
                border-radius: 14px;
                font-size: 13px;
                padding: 10px 12px;
            }
            """
        )

        outer = QVBoxLayout()
        outer.setContentsMargins(36, 36, 36, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        shell = QHBoxLayout()
        shell.setSpacing(24)

        self.hero_panel = self._build_hero_panel()
        self.auth_card = self._build_auth_card()
        self.auth_scroll = self._build_auth_scroll(self.auth_card)

        shell.addWidget(self.hero_panel, 5)
        shell.addWidget(self.auth_scroll, 4)

        outer.addLayout(shell)
        outer.addStretch(1)
        self.setLayout(outer)

        self._install_shadow(self.hero_panel, blur_radius=40)

        self.email_input.textChanged.connect(lambda *_: self._sync_action_states())
        self.password_input.textChanged.connect(lambda *_: self._sync_action_states())
        self.confirm_password_input.textChanged.connect(lambda *_: self._sync_action_states())
        self.nickname_input.textChanged.connect(lambda *_: self._sync_action_states())
        self.register_code_input.textChanged.connect(lambda *_: self._sync_action_states())

        self.login_mode_button.clicked.connect(lambda: self.set_mode("login"))
        self.register_mode_button.clicked.connect(lambda: self.set_mode("register"))
        self.login_button.clicked.connect(self._on_login_clicked)
        self.register_button.clicked.connect(self._on_register_clicked)
        self.send_code_button.clicked.connect(self._on_send_code_clicked)
        self.switch_mode_link.clicked.connect(self._toggle_mode)

        self.email_input.returnPressed.connect(self._submit_current_mode)
        self.password_input.returnPressed.connect(self._submit_current_mode)
        self.confirm_password_input.returnPressed.connect(self._submit_current_mode)
        self.nickname_input.returnPressed.connect(self._submit_current_mode)
        self.register_code_input.returnPressed.connect(self._submit_current_mode)

        self.set_mode("login")

    def _build_hero_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("heroPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel.setMinimumWidth(430)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(14)
        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setFixedSize(82, 82)
        logo_pixmap = QPixmap(str(asset_path("logo.png")))
        logo.setPixmap(
            logo_pixmap.scaled(
                82,
                82,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.eyebrow_label = QLabel(tr("login_eyebrow"))
        self.eyebrow_label.setObjectName("eyebrowLabel")
        brand_row.addWidget(logo)
        brand_row.addWidget(self.eyebrow_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self.hero_title_label = QLabel(tr("hero_title"))
        self.hero_title_label.setObjectName("heroTitle")
        self.hero_title_label.setWordWrap(True)

        self.hero_body_label = QLabel(tr("hero_body"))
        self.hero_body_label.setObjectName("heroBody")
        self.hero_body_label.setWordWrap(True)

        layout.addLayout(brand_row)
        layout.addWidget(self.hero_title_label)
        layout.addWidget(self.hero_body_label)

        self._feature_widgets = []
        for feature_title, feature_text in [
            (tr("feature_local_title"), tr("feature_local_body")),
            (tr("feature_sync_title"), tr("feature_sync_body")),
            (tr("feature_account_title"), tr("feature_account_body")),
        ]:
            pill = QFrame()
            pill.setObjectName("featurePill")
            pill_layout = QVBoxLayout(pill)
            pill_layout.setContentsMargins(16, 14, 16, 14)
            pill_layout.setSpacing(6)

            pill_title = QLabel(feature_title)
            pill_title.setObjectName("featureTitle")
            pill_text = QLabel(feature_text)
            pill_text.setObjectName("featureText")
            pill_text.setWordWrap(True)

            pill_layout.addWidget(pill_title)
            pill_layout.addWidget(pill_text)
            layout.addWidget(pill)
            self._feature_widgets.append((pill_title, pill_text))

        layout.addStretch(1)
        return panel

    def _build_auth_scroll(self, card: QFrame) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("authScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumWidth(520)
        scroll.setMinimumWidth(430)
        scroll.setWidget(card)
        return scroll

    def _build_auth_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("authCard")
        card.setMinimumWidth(420)
        card.setMaximumWidth(480)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        self.card_eyebrow = QLabel(tr("card_eyebrow"))
        self.card_eyebrow.setObjectName("cardEyebrow")

        self.card_title = QLabel(tr("card_title_login"))
        self.card_title.setObjectName("cardTitle")

        self.card_body = QLabel(tr("card_body_login"))
        self.card_body.setObjectName("cardBody")
        self.card_body.setWordWrap(True)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.login_mode_button = QPushButton(tr("mode_login"))
        self.login_mode_button.setObjectName("modeButton")
        self.login_mode_button.setCheckable(True)
        self.register_mode_button = QPushButton(tr("mode_register"))
        self.register_mode_button.setObjectName("modeButton")
        self.register_mode_button.setCheckable(True)
        mode_row.addWidget(self.login_mode_button)
        mode_row.addWidget(self.register_mode_button)

        self.email_input = self._build_line_edit(tr("field_account_placeholder"))
        self.nickname_input = self._build_line_edit(tr("field_username_placeholder"))
        self.password_input = self._build_line_edit(tr("field_password"))
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password_input = self._build_line_edit(tr("field_confirm_password"))
        self.confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.register_code_input = self._build_line_edit("6-digit code")

        layout.addWidget(self.card_eyebrow)
        layout.addWidget(self.card_title)
        layout.addWidget(self.card_body)
        layout.addLayout(mode_row)

        self.email_wrap, self.email_label = self._build_field(tr("field_account"), self.email_input)
        self.nickname_wrap, self.nickname_label = self._build_field(tr("field_username_or_nickname"), self.nickname_input)
        self.register_code_wrap, self.register_code_label = self._build_code_field()
        self.password_wrap, self.password_label = self._build_field(tr("field_password"), self.password_input)
        self.confirm_password_wrap, self.confirm_password_label = self._build_field(tr("field_confirm_password"), self.confirm_password_input)

        # Login mode: Email/Username, Password
        # Register mode: Nickname/Username, Password, Confirm Password (in user-friendly natural order)
        layout.addWidget(self.email_wrap)
        layout.addWidget(self.nickname_wrap)
        layout.addWidget(self.register_code_wrap)
        layout.addWidget(self.password_wrap)
        layout.addWidget(self.confirm_password_wrap)

        self.inline_hint_label = QLabel(tr("hint_password_len"))
        self.inline_hint_label.setObjectName("inlineHint")
        self.inline_hint_label.setWordWrap(True)

        self.login_button = QPushButton(tr("btn_login"))
        self.login_button.setObjectName("primaryAction")
        self.register_button = QPushButton(tr("btn_register"))
        self.register_button.setObjectName("primaryAction")

        self.message_label = QLabel("")
        self.message_label.setObjectName("messageLabel")
        self.message_label.setWordWrap(True)
        self.message_label.hide()

        footer_row = QHBoxLayout()
        footer_row.setSpacing(12)
        self.switch_mode_link = QPushButton()
        self.switch_mode_link.setObjectName("switchModeLink")
        self.switch_mode_link.setCursor(Qt.CursorShape.PointingHandCursor)
        footer_row.addWidget(self.switch_mode_link, 1)

        layout.addWidget(self.inline_hint_label)
        layout.addWidget(self.login_button)
        layout.addWidget(self.register_button)
        layout.addLayout(footer_row)
        layout.addWidget(self.message_label)
        layout.addStretch(1)
        return card

    @staticmethod
    def _build_line_edit(placeholder: str) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        line_edit.setFixedHeight(48)
        line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return line_edit

    @staticmethod
    def _build_field(label_text: str, widget: QWidget) -> tuple[QWidget, QLabel]:
        container = QWidget()
        container.setMinimumHeight(72)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        layout.addWidget(label)
        layout.addWidget(widget)
        return container, label

    def _build_code_field(self) -> tuple[QWidget, QLabel]:
        container = QWidget()
        container.setMinimumHeight(72)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(tr("field_code"))
        label.setObjectName("fieldLabel")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.send_code_button = QPushButton(tr("btn_send_code"))
        self.send_code_button.setObjectName("secondaryAction")
        self.send_code_button.setMinimumHeight(48)
        self.send_code_button.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.register_code_input, 1)
        row.addWidget(self.send_code_button)
        layout.addWidget(label)
        layout.addLayout(row)
        return container, label

    @staticmethod
    def _install_shadow(widget: QWidget, *, blur_radius: int) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur_radius)
        shadow.setOffset(0, 18)
        shadow.setColor(Qt.GlobalColor.black)
        widget.setGraphicsEffect(shadow)

    def _on_login_clicked(self) -> None:
        self.login_requested.emit(self.email_input.text().strip(), self.password_input.text())

    def _on_register_clicked(self) -> None:
        nickname = self.nickname_input.text().strip()
        email = self.email_input.text().strip()
        self.register_requested.emit(
            email or f"{nickname}@local",
            self.password_input.text(),
            nickname,
            self.register_code_input.text().strip(),
        )

    def _on_send_code_clicked(self) -> None:
        self.send_register_code_requested.emit(self.email_input.text().strip())

    def _toggle_mode(self) -> None:
        self.set_mode("register" if self._mode == "login" else "login")

    def _submit_current_mode(self) -> None:
        if self._mode == "login" and self.login_button.isEnabled():
            self._on_login_clicked()
        elif self._mode == "register" and self.register_button.isEnabled():
            self._on_register_clicked()

    def set_mode(self, mode: AuthMode) -> None:
        self._mode = mode
        is_register = mode == "register"
        self.login_mode_button.setChecked(not is_register)
        self.register_mode_button.setChecked(is_register)
        self.nickname_wrap.setVisible(is_register)
        self.password_wrap.setVisible(True)
        self.confirm_password_wrap.setVisible(is_register)
        self.register_code_wrap.setVisible(False)
        self.email_wrap.setVisible(not is_register)
        self.login_button.setVisible(not is_register)
        self.register_button.setVisible(is_register)

        if is_register:
            self.card_title.setText(tr("card_title_register"))
            self.card_body.setText(tr("card_body_register_simple"))
            self.nickname_label.setText(tr("field_username_or_nickname"))
            self.nickname_input.setPlaceholderText(tr("field_username_placeholder"))
            self.password_label.setText(tr("field_password"))
            self.password_input.setPlaceholderText(tr("field_password"))
            self.confirm_password_label.setText(tr("field_confirm_password"))
            self.confirm_password_input.setPlaceholderText(tr("field_confirm_password"))
            self.inline_hint_label.setText(tr("hint_register_rules"))
            self.switch_mode_link.setText(tr("switch_to_login"))
        else:
            self.card_title.setText(tr("card_title_login"))
            self.card_body.setText(tr("card_body_login"))
            self.email_label.setText(tr("field_account"))
            self.email_input.setPlaceholderText(tr("field_account_placeholder"))
            self.password_label.setText(tr("field_password"))
            self.password_input.setPlaceholderText(tr("field_password"))
            self.inline_hint_label.setText(tr("hint_password_len"))
            self.switch_mode_link.setText(tr("switch_to_register"))
        self._sync_action_states()

    def retranslate_ui(self) -> None:
        if hasattr(self, "eyebrow_label"):
            self.eyebrow_label.setText(tr("login_eyebrow"))
        if hasattr(self, "hero_title_label"):
            self.hero_title_label.setText(tr("hero_title"))
        if hasattr(self, "hero_body_label"):
            self.hero_body_label.setText(tr("hero_body"))
        if hasattr(self, "_feature_widgets"):
            feature_data = [
                (tr("feature_local_title"), tr("feature_local_body")),
                (tr("feature_sync_title"), tr("feature_sync_body")),
                (tr("feature_account_title"), tr("feature_account_body")),
            ]
            for (title_w, body_w), (ft, fb) in zip(self._feature_widgets, feature_data):
                title_w.setText(ft)
                body_w.setText(fb)
        if hasattr(self, "card_eyebrow"):
            self.card_eyebrow.setText(tr("card_eyebrow"))
        if hasattr(self, "login_mode_button"):
            self.login_mode_button.setText(tr("mode_login"))
        if hasattr(self, "register_mode_button"):
            self.register_mode_button.setText(tr("mode_register"))
        if hasattr(self, "login_button"):
            self.login_button.setText(tr("btn_login"))
        if hasattr(self, "register_button"):
            self.register_button.setText(tr("btn_register"))
        if hasattr(self, "send_code_button"):
            self.send_code_button.setText(tr("btn_send_code"))
        if hasattr(self, "register_code_label"):
            self.register_code_label.setText(tr("field_code"))
        self.set_mode(self._mode)

    def switch_to_login_with_email(self, email: str) -> None:
        self.email_input.setText(email)
        self.start_send_code_cooldown(0)
        self.set_mode("login")
        self.password_input.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in [
            self.email_input,
            self.password_input,
            self.confirm_password_input,
            self.nickname_input,
            self.register_code_input,
            self.send_code_button,
            self.login_mode_button,
            self.register_mode_button,
            self.switch_mode_link,
        ]:
            widget.setEnabled(not busy)
        self._sync_action_states()

    def set_message(self, message: str, *, error: bool = False) -> None:
        if not message:
            self.message_label.clear()
            self.message_label.hide()
            return
        if error:
            self.message_label.setStyleSheet(
                "QLabel#messageLabel { background: #fff1f1; color: #b53131; border: 1px solid #f2c6c6; }"
            )
        else:
            self.message_label.setStyleSheet(
                "QLabel#messageLabel { background: #eef7ff; color: #24507d; border: 1px solid #c8def3; }"
            )
        self.message_label.setText(message)
        self.message_label.show()

    def set_debug_code(self, code: str | None) -> None:
        _ = code

    def enter_profile_setup(self, profile_setup_token: str) -> None:
        self._profile_setup_token = profile_setup_token
        self.set_mode("register")

    def clear_profile_setup(self) -> None:
        self._profile_setup_token = None
        self.register_code_input.clear()
        self.confirm_password_input.clear()
        self.nickname_input.clear()
        self.set_mode("login")

    @property
    def profile_setup_token(self) -> str | None:
        return self._profile_setup_token

    def start_send_code_cooldown(self, seconds: int) -> None:
        self._send_code_remaining = max(0, seconds)
        if self._send_code_remaining:
            self._send_code_timer.start()
        else:
            self._send_code_timer.stop()
        self._sync_action_states()

    def _tick_send_code_cooldown(self) -> None:
        self._send_code_remaining = max(0, self._send_code_remaining - 1)
        if self._send_code_remaining == 0:
            self._send_code_timer.stop()
        self._sync_action_states()

    @staticmethod
    def _looks_like_email(email: str) -> bool:
        return bool(email) and "@" in email and "." in email

    def _sync_action_states(self) -> None:
        account = self.email_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        nickname = self.nickname_input.text().strip()

        can_login = not self._busy and bool(account) and bool(password)
        can_register = (
            not self._busy
            and len(nickname) >= 2
            and len(password) >= 6
            and confirm_password == password
        )

        self.login_button.setEnabled(can_login)
        self.register_button.setEnabled(can_register)
        self.send_code_button.setEnabled(False)
        if self._send_code_remaining:
            self.send_code_button.setText(tr("btn_resend_code", s=self._send_code_remaining))
        else:
            self.send_code_button.setText(tr("btn_send_code"))
