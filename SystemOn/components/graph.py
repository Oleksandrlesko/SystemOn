"""Графік SystemOn: швидкий QPainter (сітка ядер) або matplotlib (великі графіки)."""
from math import floor

import numpy as np

import matplotlib

matplotlib.use("Agg")
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib import pyplot as plt

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QPainterPath, QBrush, QImage
from PyQt5.QtWidgets import QLabel, QSizePolicy


def _qcolor_to_mpl(color):
    if isinstance(color, QColor):
        return color.name()
    return str(color)


class RGraph(QLabel):
    """Віджет графіка. compact=True — легкий QPainter; інакше matplotlib з кешем Figure."""

    def __init__(
        self,
        x_points: int = 10,
        y_points: int = 10,
        min: int = 0,
        max: int = 100,
        hue_offset: int = 0,
        label: str = "",
        compact: bool = False,
    ):
        super().__init__()
        self.setMinimumWidth(100)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("RGraph")
        self.x_points = x_points
        self.y_points = y_points
        self.min_val = min
        self.max_val = max
        if self.min_val > self.max_val:
            self.min_val = self.max_val - 1
        self.data = [float(min)] * (x_points + 1)
        self.hue_offset = hue_offset
        self.label = label
        self.compact = compact
        self.styling = None
        self._dirty = True
        self._last_draw_size = (0, 0)
        self._mpl_dpi = 72.0
        self._fig = None
        self._ax = None
        self._line = None
        self._fill = None
        self._canvas = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_debounced)

    def resizeEvent(self, event):
        self._resize_timer.start(120)
        super().resizeEvent(event)

    def _on_resize_debounced(self):
        w, h = self.width(), self.height()
        if (w, h) != self._last_draw_size:
            self._dirty = True
            self._last_draw_size = (0, 0)
            if not self.compact:
                self._dispose_mpl()
        self.flush_draw()

    def request_redraw(self):
        self._dirty = True

    def flush_draw(self):
        if not self._dirty or not self.styling:
            return
        if not self.isVisible():
            return
        self.drawGraph()
        self._dirty = False

    def mark_styling_dirty(self):
        self._dirty = True
        if not self.compact:
            self._dispose_mpl()

    def _dispose_mpl(self):
        if self._fig is not None:
            plt.close(self._fig)
        self._fig = None
        self._ax = None
        self._line = None
        self._fill = None
        self._canvas = None

    def drawGraph(self):
        if not self.styling:
            return
        width, height = self.size().width(), self.size().height()
        if width <= 0 or height <= 0:
            return
        if self.compact:
            self._draw_qpainter(width, height)
        else:
            self._draw_matplotlib(width, height)
        self._last_draw_size = (width, height)

    def _draw_qpainter(self, width, height):
        pixmap = QPixmap(width, height)
        pixmap.fill(self.styling[0])
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        line_amount_x = max(1, floor((width - (width % 40)) / 40))
        line_amount_y = max(1, floor((height - (height % 40)) / 40))
        line_distance_x = width / line_amount_x
        line_distance_y = height / line_amount_y
        pen = QPen(self.styling[1], 1)
        painter.setPen(pen)
        for i in range(1, line_amount_x):
            x_pos = round(line_distance_x * i)
            painter.drawLine(x_pos, 0, x_pos, height)
        for i in range(1, line_amount_y):
            y_pos = round(line_distance_y * i)
            painter.drawLine(0, y_pos, width, y_pos)
        pen = QPen(self.styling[2], 1)
        painter.setPen(pen)
        painter.drawRect(0, 0, width - 1, height - 1)
        val_range = max(1e-6, self.max_val - self.min_val)
        data_point_distance_x = width / max(1, self.x_points)
        drawable_height = height - 2
        painter.setPen(QPen(self.styling[2]))
        painter.drawText(4, 12, self.label)
        path = QPainterPath()
        first_y = round(drawable_height - ((self.data[0] - self.min_val) / val_range) * drawable_height) + 2
        path.moveTo(0, first_y)
        last_x = 0
        for i, point in enumerate(self.data):
            x_pos = round(data_point_distance_x * i)
            y_pos = round(drawable_height - ((point - self.min_val) / val_range) * drawable_height) + 2
            path.lineTo(x_pos, y_pos)
            last_x = x_pos
        path.lineTo(last_x, height)
        path.lineTo(0, height)
        path.closeSubpath()
        fill_color = QColor(self.styling[3])
        fill_color.setAlpha(48)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)
        pen = QPen(self.styling[3], 1)
        painter.setPen(pen)
        prev_point = None
        for i, point in enumerate(self.data):
            x_pos = round(data_point_distance_x * i)
            y_pos = round(drawable_height - ((point - self.min_val) / val_range) * drawable_height) + 2
            if prev_point is not None:
                painter.drawLine(prev_point[0], prev_point[1], x_pos, y_pos)
            prev_point = (x_pos, y_pos)
        painter.end()
        self.setPixmap(pixmap)

    def _draw_matplotlib(self, width, height):
        bg = _qcolor_to_mpl(self.styling[0])
        grid = _qcolor_to_mpl(self.styling[1])
        border = _qcolor_to_mpl(self.styling[2])
        line = _qcolor_to_mpl(self.styling[3])

        fig_w = width / self._mpl_dpi
        fig_h = height / self._mpl_dpi
        size_changed = (
            self._fig is None
            or abs(self._fig.get_figwidth() - fig_w) > 0.05
            or abs(self._fig.get_figheight() - fig_h) > 0.05
        )

        if size_changed:
            self._dispose_mpl()
            self._fig = Figure(figsize=(fig_w, fig_h), dpi=self._mpl_dpi)
            self._fig.patch.set_facecolor(bg)
            self._ax = self._fig.add_subplot(111)
            self._ax.set_facecolor(bg)
            x = np.arange(len(self.data))
            y = np.asarray(self.data, dtype=float)
            self._fill = self._ax.fill_between(
                x, self.min_val, y, color=line, alpha=0.22, linewidth=0
            )
            (self._line,) = self._ax.plot(x, y, color=line, linewidth=1.4, antialiased=True)
            self._ax.set_xlim(0, max(1, len(self.data) - 1))
            self._ax.set_ylim(self.min_val, self.max_val)
            self._ax.set_title(self.label, color=border, fontsize=9, loc="left", pad=4)
            self._ax.grid(True, color=grid, alpha=0.45, linewidth=0.7)
            self._ax.tick_params(colors=border, labelsize=7, length=3)
            for spine in self._ax.spines.values():
                spine.set_color(border)
            self._fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.14)
            self._canvas = FigureCanvasAgg(self._fig)
        else:
            y = np.asarray(self.data, dtype=float)
            x = np.arange(len(y))
            self._line.set_data(x, y)
            try:
                self._fill.remove()
            except Exception:
                pass
            self._fill = self._ax.fill_between(
                x, self.min_val, y, color=line, alpha=0.22, linewidth=0
            )
            self._ax.set_ylim(self.min_val, self.max_val)
            self._ax.set_title(self.label, color=border, fontsize=9, loc="left", pad=4)

        self._canvas.draw()
        w_px, h_px = self._canvas.get_width_height()
        rgba = np.asarray(self._canvas.buffer_rgba(), dtype=np.uint8).reshape((h_px, w_px, 4))
        image = QImage(rgba.data, w_px, h_px, w_px * 4, QImage.Format_RGBA8888)
        self.setPixmap(QPixmap.fromImage(image.copy()))

    def set_label(self, label: str):
        if self.label != label:
            self.label = label
            self.mark_styling_dirty()

    def push_value(self, value: float = 0.0):
        """Оновити буфер без перемальовки (для пакетного flush)."""
        append_value = float(self.min_val if value is None else value)
        self.data.pop(0)
        self.data.append(append_value)
        self._dirty = True

    def updateLatestDatapoint(self, value: float = 0.0):
        self.push_value(value)
        self.request_redraw()

    def get_styling(self):
        palette = self.palette()
        background_color = QColor(palette.color(self.backgroundRole()).name())
        foreground_color = QColor(palette.color(self.foregroundRole()).name())
        bh, bs, bl, _ = background_color.getHsl()
        fh, fs, fl, _ = foreground_color.getHsl()
        fh = (fh + self.hue_offset) % 360
        if bl > 128:
            bl = max(0, bl - 13)
        else:
            bl = min(255, bl + 13)
        bg_secondary = QColor()
        bg_border = QColor()
        bg_secondary.setHsl(bh, bs, bl)
        bg_border.setHsl(bh, bs, 32 if bl > 128 else 224)
        foreground_color.setHsl(fh, fs, fl)
        return [background_color, bg_secondary, bg_border, foreground_color]

    def showEvent(self, event):
        if self.styling is None:
            self.styling = self.get_styling()
        self.request_redraw()
        super().showEvent(event)
