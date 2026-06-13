"""진입점. docker 소켓 연결 실패 시 안내 후 종료."""

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    from app.ui.theme import STYLESHEET
    app.setStyleSheet(STYLESHEET)
    try:
        window = MainWindow()
    except Exception as exc:  # docker.from_env 실패 등
        QMessageBox.critical(None, "초기화 실패", f"도커 연결 실패: {exc}")
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
