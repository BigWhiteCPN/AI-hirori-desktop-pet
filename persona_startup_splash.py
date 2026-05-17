import argparse
import math
import os
import sys
import time

from PyQt5.QtCore import QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRegion
from PyQt5.QtWidgets import QApplication, QDialog


class StartupSplashWindow(QDialog):
    def __init__(self, sentinel_path="", max_seconds=180.0):
        super().__init__()
        self._sentinel_path = sentinel_path
        self._started_at = time.monotonic()
        self._max_seconds = float(max_seconds)
        self._tick = 0

        self.setWindowTitle("唤醒苏念")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setWindowModality(Qt.ApplicationModal)

        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._advance_animation)
        self._animation_timer.start(32)

        self._close_timer = QTimer(self)
        self._close_timer.timeout.connect(self._poll_close_signal)
        self._close_timer.start(120)

        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._keep_front)
        self._raise_timer.start(180)

    def _advance_animation(self):
        self._tick = (self._tick + 1) % 360
        self.update()

    def _keep_front(self):
        self.raise_()
        self.activateWindow()

    def _poll_close_signal(self):
        if self._sentinel_path and os.path.exists(self._sentinel_path):
            try:
                os.remove(self._sentinel_path)
            except OSError:
                pass
            self.accept()
            return
        if (time.monotonic() - self._started_at) > self._max_seconds:
            self.accept()

    def _update_rounded_mask(self):
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 34, 34)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def showEvent(self, event):
        super().showEvent(event)
        self._update_rounded_mask()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_rounded_mask()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 244, 250, 255))

        panel_rect = QRectF(14, 14, self.width() - 28, self.height() - 28)
        shadow_rect = QRectF(panel_rect)
        shadow_rect.translate(0, 8)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(shadow_rect, 36, 36)
        painter.fillPath(shadow_path, QColor(88, 47, 74, 52))

        gradient = QLinearGradient(panel_rect.left(), panel_rect.top(), panel_rect.right(), panel_rect.bottom())
        gradient.setColorAt(0.0, QColor(255, 247, 252, 248))
        gradient.setColorAt(0.38, QColor(255, 239, 247, 244))
        gradient.setColorAt(1.0, QColor(255, 226, 239, 242))
        panel_path = QPainterPath()
        panel_path.addRoundedRect(panel_rect, 36, 36)
        painter.fillPath(panel_path, gradient)
        painter.setPen(QPen(QColor(229, 133, 180, 205), 1.4))
        painter.drawPath(panel_path)

        content_top = panel_rect.top() + max(26.0, (panel_rect.height() - 384.0) / 2.0)

        badge_rect = QRectF(panel_rect.left() + 28, content_top, 104, 32)
        badge_path = QPainterPath()
        badge_path.addRoundedRect(badge_rect, 16, 16)
        painter.fillPath(badge_path, QColor(255, 255, 255, 198))
        painter.setPen(QColor(170, 88, 130))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        painter.drawText(badge_rect, Qt.AlignCenter, "唤醒")

        spinner_center_x = panel_rect.left() + 100
        spinner_center_y = content_top + 112
        spinner_rect = QRectF(spinner_center_x - 42, spinner_center_y - 42, 84, 84)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(248, 208, 226, 188), 10))
        painter.drawEllipse(spinner_rect)

        painter.setPen(QPen(QColor(225, 104, 160), 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(spinner_rect, int((-self._tick - 20) * 16), 112 * 16)

        orbit_radius = 56
        for index in range(3):
            angle = math.radians(self._tick * 1.6 + index * 120.0)
            dot_x = spinner_center_x + math.cos(angle) * orbit_radius
            dot_y = spinner_center_y + math.sin(angle) * orbit_radius * 0.62
            radius = 7 if index == 0 else 5
            alpha = 240 if index == 0 else 168
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(237, 112, 167, alpha))
            painter.drawEllipse(QRectF(dot_x - radius, dot_y - radius, radius * 2, radius * 2))

        painter.setPen(QColor(96, 52, 77))
        painter.setFont(QFont("Microsoft YaHei UI", 17, QFont.Bold))
        painter.drawText(
            QRectF(panel_rect.left() + 172, content_top + 40, panel_rect.width() - 206, 34),
            Qt.AlignLeft | Qt.AlignVCenter,
            "唤醒苏念",
        )

        painter.setPen(QColor(143, 73, 110))
        painter.setFont(QFont("Microsoft YaHei UI", 10))
        painter.drawText(
            QRectF(panel_rect.left() + 172, content_top + 80, panel_rect.width() - 206, 64),
            Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
            "正在准备角色界面、动作模型和语音能力。",
        )

        status_rect = QRectF(panel_rect.left() + 28, content_top + 196, panel_rect.width() - 56, 46)
        status_path = QPainterPath()
        status_path.addRoundedRect(status_rect, 18, 18)
        painter.fillPath(status_path, QColor(255, 255, 255, 198))
        painter.setPen(QColor(163, 82, 122))
        painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.DemiBold))
        painter.drawText(
            status_rect.adjusted(18, 0, -18, 0),
            Qt.AlignLeft | Qt.AlignVCenter,
            "加载中，请稍等...",
        )

        painter.setPen(QColor(176, 101, 134))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(
            QRectF(panel_rect.left() + 28, content_top + 252, panel_rect.width() - 56, 84),
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
            "加载 Live2D 时主程序可能会短暂繁忙，动画会保持在独立窗口中运行。",
        )
        painter.end()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--x", type=int, default=200)
    parser.add_argument("--y", type=int, default=120)
    parser.add_argument("--width", type=int, default=420)
    parser.add_argument("--height", type=int, default=560)
    parser.add_argument("--sentinel", default="")
    parser.add_argument("--parent-pid", default="")
    return parser.parse_args()


def main():
    args = parse_args()
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    splash = StartupSplashWindow(sentinel_path=args.sentinel)
    splash.setGeometry(args.x, args.y, args.width, args.height)
    splash.show()
    splash.raise_()
    splash.activateWindow()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
