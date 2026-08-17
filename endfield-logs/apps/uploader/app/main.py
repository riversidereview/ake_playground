import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.ui.assets import app_icon
from app.ui.main_window import MainWindow


def _configure_logging() -> None:
    appdata_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".endfield-pcap")
    log_dir = appdata_root / "EndfieldPCAP" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "uploader.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    previous_hook = sys.excepthook

    def _log_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
        logging.getLogger(__name__).critical(
            "unhandled uploader exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = _log_unhandled_exception


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="EndfieldLogsUploader", add_help=True)
    parser.add_argument("--open-log", dest="open_log", help="启动后直接载入指定日志文件。")
    parser.add_argument("--watch-log", dest="watch_log", help="启动后持续监听统一客户端自动归档的日志文件。")
    parser.add_argument("--auto-parse", dest="auto_parse", action="store_true", help="载入日志后自动开始解析。")
    parser.add_argument(
        "--auto-upload-all",
        dest="auto_upload_all",
        action="store_true",
        help="解析完成后自动上传所有当前可上传的候选 battle。",
    )
    return parser


def main() -> int:
    _configure_logging()
    parser = _build_arg_parser()
    args = parser.parse_args(sys.argv[1:])

    app = QApplication(sys.argv[:1])
    app.setWindowIcon(app_icon())
    window = MainWindow()
    window.show()
    if args.watch_log:
        watched_log = str(Path(args.watch_log).expanduser())
        QTimer.singleShot(0, lambda: window.run_managed_log_workflow(watched_log))
    elif args.open_log:
        startup_log = str(Path(args.open_log).expanduser())
        QTimer.singleShot(
            0,
            lambda: window.run_startup_log_workflow(
                startup_log,
                auto_parse=args.auto_parse or args.auto_upload_all,
                auto_upload=args.auto_upload_all,
            ),
        )
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
