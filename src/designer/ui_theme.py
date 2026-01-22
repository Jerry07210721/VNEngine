# -*- coding: utf-8 -*-
"""VNEngine UI theme (white + orange #FB8138).

UI-only module: provides a single entrypoint to apply a commercial-looking
theme via Qt Fusion + QSS. Must not change any business logic.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleFactory,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
)


PRIMARY = "#FB8138"


class VNEngineStyle(QProxyStyle):
    """UI-only style tweaks.

    Important: keep this purely cosmetic and conservative.
    """

    def drawPrimitive(self, element: QStyle.PrimitiveElement, option, painter: QPainter, widget=None) -> None:  # type: ignore[override]
        if element in (
            QStyle.PrimitiveElement.PE_IndicatorArrowDown,
            QStyle.PrimitiveElement.PE_IndicatorArrowUp,
            QStyle.PrimitiveElement.PE_IndicatorArrowLeft,
            QStyle.PrimitiveElement.PE_IndicatorArrowRight,
            QStyle.PrimitiveElement.PE_IndicatorSpinUp,
            QStyle.PrimitiveElement.PE_IndicatorSpinDown,
            QStyle.PrimitiveElement.PE_IndicatorSpinPlus,
            QStyle.PrimitiveElement.PE_IndicatorSpinMinus,
        ):
            rect = option.rect
            if rect.isNull():
                return

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
            is_enabled = bool(option.state & QStyle.StateFlag.State_Enabled)

            if not is_enabled:
                color = QColor("#C7CDD6")
            elif is_hover:
                color = QColor(PRIMARY)
            else:
                color = QColor("#6B7280")

            pen = QPen(color, 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)

            cx = rect.center().x()
            cy = rect.center().y()
            size = max(4, min(rect.width(), rect.height()) // 3)

            if element == QStyle.PrimitiveElement.PE_IndicatorArrowDown:
                painter.drawLine(cx - size, cy - 1, cx, cy + size)
                painter.drawLine(cx, cy + size, cx + size, cy - 1)
            elif element == QStyle.PrimitiveElement.PE_IndicatorArrowUp:
                painter.drawLine(cx - size, cy + 1, cx, cy - size)
                painter.drawLine(cx, cy - size, cx + size, cy + 1)
            elif element == QStyle.PrimitiveElement.PE_IndicatorArrowLeft:
                painter.drawLine(cx + 1, cy - size, cx - size, cy)
                painter.drawLine(cx - size, cy, cx + 1, cy + size)
            elif element == QStyle.PrimitiveElement.PE_IndicatorArrowRight:
                painter.drawLine(cx - 1, cy - size, cx + size, cy)
                painter.drawLine(cx + size, cy, cx - 1, cy + size)
            elif element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
                painter.drawLine(cx - size, cy + 1, cx, cy - size)
                painter.drawLine(cx, cy - size, cx + size, cy + 1)
            elif element == QStyle.PrimitiveElement.PE_IndicatorSpinDown:
                painter.drawLine(cx - size, cy - 1, cx, cy + size)
                painter.drawLine(cx, cy + size, cx + size, cy - 1)
            elif element == QStyle.PrimitiveElement.PE_IndicatorSpinPlus:
                painter.drawLine(cx - size, cy, cx + size, cy)
                painter.drawLine(cx, cy - size, cx, cy + size)
            else:  # PE_IndicatorSpinMinus
                painter.drawLine(cx - size, cy, cx + size, cy)

            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)

    def drawComplexControl(self, control: QStyle.ComplexControl, option, painter: QPainter, widget=None) -> None:  # type: ignore[override]
        if control == QStyle.ComplexControl.CC_SpinBox and isinstance(option, QStyleOptionSpinBox):
            up_rect = self.subControlRect(control, option, QStyle.SubControl.SC_SpinBoxUp, widget)
            down_rect = self.subControlRect(control, option, QStyle.SubControl.SC_SpinBoxDown, widget)

            if up_rect.isValid() and down_rect.isValid():
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

                # Frame (rounded)
                outer = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5)
                has_focus = bool(option.state & QStyle.StateFlag.State_HasFocus)
                border = QColor(PRIMARY) if has_focus else QColor("#E5E7EB")
                painter.setPen(QPen(border, 1))
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawRoundedRect(outer, 8.0, 8.0)

                total = up_rect.united(down_rect)
                radius = 8.0

                # Clip path: only the OUTER right corners are rounded.
                clip = QPainterPath()
                r = QRectF(total)
                clip.moveTo(r.left(), r.top())
                clip.lineTo(r.right() - radius, r.top())
                clip.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
                clip.lineTo(r.right(), r.bottom() - radius)
                clip.quadTo(r.right(), r.bottom(), r.right() - radius, r.bottom())
                clip.lineTo(r.left(), r.bottom())
                clip.closeSubpath()
                painter.setClipPath(clip)

                is_enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
                is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
                active = option.activeSubControls

                def paint_btn(rect, is_up: bool) -> None:
                    hovered = is_hover and bool(active & (QStyle.SubControl.SC_SpinBoxUp if is_up else QStyle.SubControl.SC_SpinBoxDown))
                    pressed = bool(option.state & QStyle.StateFlag.State_Sunken) and bool(
                        active & (QStyle.SubControl.SC_SpinBoxUp if is_up else QStyle.SubControl.SC_SpinBoxDown)
                    )

                    if not is_enabled:
                        bg = QColor("#F9FAFB")
                        fg = QColor("#C7CDD6")
                    else:
                        bg = QColor("#FFE9DC") if pressed else (QColor("#FFF7F1") if hovered else QColor("#FFFFFF"))
                        fg = QColor(PRIMARY) if hovered else QColor("#6B7280")

                    painter.fillRect(rect, bg)

                    # Chevron
                    pen = QPen(fg, 1.6)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(pen)

                    cx = rect.center().x()
                    cy = rect.center().y()
                    size = max(4, min(rect.width(), rect.height()) // 4)

                    if is_up:
                        painter.drawLine(cx - size, cy + 1, cx, cy - size)
                        painter.drawLine(cx, cy - size, cx + size, cy + 1)
                    else:
                        painter.drawLine(cx - size, cy - 1, cx, cy + size)
                        painter.drawLine(cx, cy + size, cx + size, cy - 1)

                paint_btn(up_rect, True)
                paint_btn(down_rect, False)

                # Divider lines (keep inside the clipped rounded shape)
                painter.setPen(QPen(QColor("#E5E7EB"), 1))
                painter.drawLine(total.left(), up_rect.bottom(), total.right(), up_rect.bottom())
                painter.drawLine(total.left(), total.top(), total.left(), total.bottom())

                painter.restore()
            return

        if control == QStyle.ComplexControl.CC_ComboBox and isinstance(option, QStyleOptionComboBox):
            arrow_rect = self.subControlRect(control, option, QStyle.SubControl.SC_ComboBoxArrow, widget)
            if arrow_rect.isValid():
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

                # Frame (rounded)
                outer = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5)
                has_focus = bool(option.state & QStyle.StateFlag.State_HasFocus)
                border = QColor(PRIMARY) if has_focus else QColor("#E5E7EB")
                painter.setPen(QPen(border, 1))
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawRoundedRect(outer, 8.0, 8.0)

                is_enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
                is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
                hovered = is_hover and bool(option.activeSubControls & QStyle.SubControl.SC_ComboBoxArrow)

                if not is_enabled:
                    bg = QColor("#F9FAFB")
                    fg = QColor("#C7CDD6")
                else:
                    bg = QColor("#FFF7F1") if hovered else QColor("#FFFFFF")
                    fg = QColor(PRIMARY) if hovered else QColor("#6B7280")

                # Clip to right-side rounded corners (matches the input border radius)
                radius = 8.0
                r = QRectF(arrow_rect)
                clip = QPainterPath()
                clip.moveTo(r.left(), r.top())
                clip.lineTo(r.right() - radius, r.top())
                clip.quadTo(r.right(), r.top(), r.right(), r.top() + radius)
                clip.lineTo(r.right(), r.bottom() - radius)
                clip.quadTo(r.right(), r.bottom(), r.right() - radius, r.bottom())
                clip.lineTo(r.left(), r.bottom())
                clip.closeSubpath()
                painter.setClipPath(clip)

                painter.fillRect(arrow_rect, bg)

                painter.setPen(QPen(QColor("#E5E7EB"), 1))
                painter.drawLine(arrow_rect.left(), arrow_rect.top(), arrow_rect.left(), arrow_rect.bottom())

                pen = QPen(fg, 1.6)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)

                cx = arrow_rect.center().x()
                cy = arrow_rect.center().y()
                size = max(4, min(arrow_rect.width(), arrow_rect.height()) // 4)
                painter.drawLine(cx - size, cy - 1, cx, cy + size)
                painter.drawLine(cx, cy + size, cx + size, cy - 1)

                painter.restore()
            return

        # Default rendering for everything else.
        super().drawComplexControl(control, option, painter, widget)

    def subControlRect(self, control: QStyle.ComplexControl, option, subControl: QStyle.SubControl, widget=None):  # type: ignore[override]
        # Make SpinBox/ComboBox button areas match our commercial theme.
        if control == QStyle.ComplexControl.CC_SpinBox and isinstance(option, QStyleOptionSpinBox):
            total = option.rect
            btn_w = 22
            frame = 1

            inner_h = max(1, total.height() - 2 * frame)
            up_h = max(1, inner_h // 2)
            down_h = max(1, inner_h - up_h)

            if option.direction == Qt.LayoutDirection.RightToLeft:
                btn_x = total.left() + frame
                edit_left = total.left() + frame + btn_w
                edit_right = total.right() - frame
            else:
                btn_x = total.right() - btn_w - frame + 1
                edit_left = total.left() + frame
                edit_right = total.right() - btn_w - frame

            if subControl == QStyle.SubControl.SC_SpinBoxUp:
                return QRect(btn_x, total.top() + frame, btn_w, up_h)

            if subControl == QStyle.SubControl.SC_SpinBoxDown:
                return QRect(btn_x, total.top() + frame + up_h, btn_w, down_h)

            if subControl == QStyle.SubControl.SC_SpinBoxEditField:
                return QRect(edit_left, total.top() + frame, max(1, edit_right - edit_left + 1), inner_h)

        if control == QStyle.ComplexControl.CC_ComboBox and isinstance(option, QStyleOptionComboBox):
            total = option.rect
            arrow_w = 30
            frame = 1

            inner_h = max(1, total.height() - 2 * frame)

            if option.direction == Qt.LayoutDirection.RightToLeft:
                arrow_x = total.left() + frame
                edit_left = total.left() + frame + arrow_w
                edit_right = total.right() - frame
            else:
                arrow_x = total.right() - arrow_w - frame + 1
                edit_left = total.left() + frame
                edit_right = total.right() - arrow_w - frame

            if subControl == QStyle.SubControl.SC_ComboBoxArrow:
                return QRect(arrow_x, total.top() + frame, arrow_w, inner_h)
            if subControl == QStyle.SubControl.SC_ComboBoxEditField:
                return QRect(edit_left, total.top() + frame, max(1, edit_right - edit_left + 1), inner_h)

        return super().subControlRect(control, option, subControl, widget)


def _build_palette() -> QPalette:
    p = QPalette()

    # Base surfaces
    p.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#FFF7F1"))

    # Text
    p.setColor(QPalette.ColorRole.WindowText, QColor("#111827"))
    p.setColor(QPalette.ColorRole.Text, QColor("#111827"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9CA3AF"))

    # Buttons
    p.setColor(QPalette.ColorRole.Button, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#111827"))

    # Accent
    p.setColor(QPalette.ColorRole.Highlight, QColor(PRIMARY))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))

    return p


def vnengine_qss() -> str:
    # NOTE: Keep QSS conservative to avoid breaking custom-painted widgets.
    return f"""
/* ===== VNEngine Commercial Theme ===== */

* {{
    font-family: 'Segoe UI', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
    font-size: 12px;
    color: #111827;
}}

QMainWindow, QDialog {{
    background: #FFFFFF;
}}

QLabel[role="title"] {{
    font-size: 18px;
    font-weight: 700;
    color: #111827;
}}

QLabel[role="subtitle"] {{
    font-size: 11px;
    color: #6B7280;
}}

QLabel[pill="true"] {{
    background: #FFF7F1;
    border: 1px solid #E5E7EB;
    border-radius: 999px;
    padding: 4px 10px;
    color: #6B7280;
}}

QFrame[card="true"] {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
}}

QLabel[role="cardTitle"] {{
    font-size: 14px;
    font-weight: 700;
    color: #111827;
}}

QPushButton {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 30px;
}}
QPushButton:hover {{
    background: #FFF7F1;
    border-color: #F3C2A3;
}}
QPushButton:pressed {{
    background: #FFE9DC;
}}
QPushButton:disabled {{
    color: #9CA3AF;
    background: #F9FAFB;
    border-color: #EEF2F7;
}}

QPushButton[variant="primary"] {{
    background: {PRIMARY};
    border-color: {PRIMARY};
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: #FF944D;
    border-color: #FF944D;
}}
QPushButton[variant="primary"]:pressed {{
    background: #E46F2D;
    border-color: #E46F2D;
}}

QPushButton[variant="danger"] {{
    background: #FFFFFF;
    border-color: #FCA5A5;
    color: #B91C1C;
    font-weight: 600;
}}
QPushButton[variant="danger"]:hover {{
    background: #FEF2F2;
    border-color: #F87171;
}}

QCommandLinkButton {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    padding: 12px 14px;
    text-align: left;
}}
QCommandLinkButton[variant="primary"] {{
    border: 1px solid {PRIMARY};
}}
QCommandLinkButton[variant="danger"] {{
    border: 1px solid #FCA5A5;
}}
QCommandLinkButton:hover {{
    background: #FFF7F1;
    border-color: #F3C2A3;
}}
QCommandLinkButton[variant="primary"]:hover {{
    border-color: {PRIMARY};
}}
QCommandLinkButton[variant="danger"]:hover {{
    background: #FEF2F2;
    border-color: #F87171;
}}
QCommandLinkButton:pressed {{
    background: #FFE9DC;
}}

QLineEdit {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
    min-height: 30px;
}}
QPlainTextEdit, QTextEdit {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {PRIMARY};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {PRIMARY};
}}

/* NOTE: We intentionally do NOT set ::up-arrow/::down-arrow images here.
    Arrows are painted by VNEngineStyle so we avoid any resource/URI issues.
*/

QTabWidget::pane {{
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    top: -1px;
}}
QTabBar::tab {{
    background: #FFFFFF;
    border: 1px solid transparent;
    padding: 8px 14px;
    margin: 2px 2px 0px 2px;
    color: #374151;
}}
QTabBar::tab:selected {{
    color: {PRIMARY};
    font-weight: 600;
    border-bottom: 2px solid {PRIMARY};
}}
QTabBar::tab:hover {{
    background: #FFF7F1;
}}

QMenuBar {{
    background: #FFFFFF;
}}
QMenuBar::item:selected {{
    background: #FFF7F1;
    border-radius: 6px;
}}
QMenu {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: #FFF7F1;
}}

QToolBar {{
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
    spacing: 8px;
    padding: 6px;
}}

QStatusBar {{
    background: #FFFFFF;
    border-top: 1px solid #E5E7EB;
    color: #6B7280;
}}

QDockWidget {{
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
}}
QDockWidget::title {{
    background: #FFF7F1;
    padding: 6px 10px;
    border-bottom: 1px solid #E5E7EB;
    font-weight: 600;
}}

QScrollArea {{
    border: none;
}}

QListWidget {{
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 8px;
}}
QListWidget::item:selected {{
    background: #FFF7F1;
    color: #111827;
    border: 1px solid #F3C2A3;
}}
"""


def apply_vnengine_theme(app: QApplication) -> None:
    """Apply VNEngine theme to the given QApplication.

    Safe to call multiple times.
    """
    if app is None:
        return

    try:
        base_style = QStyleFactory.create("Fusion")
        app.setStyle(VNEngineStyle(base_style))
    except Exception:
        # If platform style fails, keep default.
        pass

    try:
        app.setPalette(_build_palette())
    except Exception:
        pass

    # Avoid clobbering other stylesheets by appending.
    qss = vnengine_qss()
    existing = app.styleSheet() or ""
    if "VNEngine Commercial Theme" in existing:
        return
    app.setStyleSheet((existing + "\n\n" + qss).strip())
