import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.assets import app_icon


DOWNLOAD_URL = "https://zmdlogs.com"


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())

    box = QMessageBox()
    box.setWindowTitle("Endfield Logs 上传器已合并")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText("独立上传器已合并到终末地战斗日志客户端。")
    box.setInformativeText("请下载并使用新版统一客户端。")
    download_button = box.addButton("打开下载页", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("退出", QMessageBox.ButtonRole.RejectRole)
    box.exec()

    if box.clickedButton() == download_button:
        QDesktopServices.openUrl(QUrl(DOWNLOAD_URL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
