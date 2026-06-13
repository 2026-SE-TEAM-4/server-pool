"""다크 모던 테마: 전역 QSS와 메트릭 임계 색상.

main.py에서 app.setStyleSheet(STYLESHEET)로 적용한다. 색은 한곳에서 관리한다.
"""

BG = "#15171c"
SURFACE = "#1e2128"
SURFACE_HI = "#242832"
BORDER = "#2c313c"
TEXT = "#e6e8ec"
MUTED = "#9aa0aa"
ACCENT = "#4f9cf9"
ACCENT_HI = "#6cb0ff"

# 메트릭 임계 색상.
OK = "#3ddc97"
WARN = "#f5a623"
CRIT = "#ff5c5c"


def level_color(value) -> str:
    """사용률 값에 따른 색. None이면 뮤트."""
    if value is None:
        return MUTED
    if value >= 90:
        return CRIT
    if value >= 70:
        return WARN
    return OK


STYLESHEET = f"""
* {{
    font-family: "Pretendard", "Noto Sans KR", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QWidget {{ background: {BG}; }}
QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {MUTED};
    font-weight: 600;
}}
QPushButton {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
}}
QPushButton:hover {{ background: {BORDER}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: #0c0e12; }}
QComboBox, QSpinBox {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 8px;
}}
QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px; background: {BORDER}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 14px; height: 14px;
    margin: -6px 0; border-radius: 7px;
}}
QTableWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    selection-background-color: {SURFACE_HI};
}}
QHeaderView::section {{
    background: {SURFACE_HI};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
}}
QPlainTextEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {MUTED};
}}
QRadioButton {{ spacing: 6px; }}
"""
