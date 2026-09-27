# -*- coding: utf-8 -*-
"""主窗口：无边框半透明频谱窗口 + 托盘 + 设置。

对应原单文件中的 ``Visualizer`` 类，逻辑逐字保留，仅做四处结构性改动：

1. 不再引用模块级 ``CFG`` 全局变量，改为从 ``visualizer.config`` 导入
   共享实例 ``cfg``；``save_config(CFG)`` 改为 ``cfg.save()``。
2. ``tr`` 从 ``visualizer.i18n`` 导入。
3. ``AudioThread`` / ``MediaThread`` 从 ``visualizer.core`` 导入。
4. pin 图标绘制改为调用 ``visualizer.ui.icons.make_pin_icon``，原静态
   方法 ``_make_pin_icon`` 逻辑被搬到了该模块（行为完全一致）。
"""

from __future__ import annotations

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets

from ..config import cfg
from ..core import AudioThread, MediaThread
from ..i18n import tr
from .icons import make_pin_icon
from .settings_dialog import SettingsDialog


class Visualizer(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        flags = QtCore.Qt.WindowType.FramelessWindowHint
        if cfg["display_mode"] == "top":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # pin 状态：display_mode 为 top 时视为初始已固定
        self._pinned = cfg["display_mode"] == "top"
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(cfg["win_w"], cfg["win_h"] + cfg["title_area"])
        self.move(cfg["win_x"], cfg["win_y"])

        self.color = QtGui.QColor(*cfg["fixed_color"])
        self._cached_rgb = None          # 上次构建画刷用的 (r,g,b)
        self._grad_top = None            # 缓存的渐变顶部颜色
        self._grad_bot = None            # 缓存的渐变底部颜色
        self._solid = None               # 缓存的纯色
        self._grad = QtGui.QLinearGradient()   # 复用的渐变对象（Gradient Pool）
        # 标题字体与度量只建一次，避免每帧重建
        self._title_font = QtGui.QFont()
        self._title_font.setFamilies(["Georgia", "SimSun"])
        self._title_font.setPointSize(13)
        self._title_font.setItalic(True)
        self._title_fm = QtGui.QFontMetrics(self._title_font)
        self._title_cache_text = None    # 上次计算包围盒时的文本
        self._title_base_rect = QtCore.QRect()  # 缓存的原始包围盒
        self._last_bars = None           # 上次重绘时的音柱高度快照
        self._dirty = True               # 颜色/标题/拖拽变化时强制重绘
        # 像素对齐布局缓存（修复音柱粗细/间隙不均），键为 (w,h,n,gap,min_bar,dpr)
        self._layout_key = None
        self._step_p = 1                 # 统一柱距（物理像素，整数）
        self._bar_w_p = 1                # 所有柱子统一的宽度（物理像素，整数）
        self._n_disp = 1                 # 显示柱数（恰好铺满窗口）
        self._src_xs = None              # 源音柱横坐标（插值用）
        self._disp_xs = None             # 显示柱横坐标（插值用，None=不插值）
        self._area_p = 1                 # 音柱区高度（物理像素，整数）
        self._min_h_p = 1                # 最小音柱高度（物理像素，整数）
        self.song_title = ""
        self._drag_pos = None
        self._drag_title = False
        self._title_off = QtCore.QPoint()
        self._title_rect = QtCore.QRect()
        self.settings_win = None

        self.audio = AudioThread(cfg["num_bars"])
        self.media = MediaThread()
        self.media.color_ready.connect(self.on_color)
        self.media.title_ready.connect(self.on_title)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        QtCore.QTimer.singleShot(200, self._start_workers)

    def _start_workers(self):
        self.audio.start()
        self.media.start()
        self._make_buttons()
        self._make_tray()
        self.apply_color_mode()
        # 停在桌面模式：启动时把窗口沉到最底层，不再动窗口父子关系
        if cfg["display_mode"] == "desktop":
            self.lower()

    def _make_buttons(self):
        style = ("QPushButton{background:rgba(0,0,0,110);color:white;"
                 "border:none;border-radius:9px;font-size:12px;}"
                 "QPushButton:hover{background:rgba(0,0,0,190);}")
        self.btn_min = QtWidgets.QPushButton("—", self)
        self.btn_close = QtWidgets.QPushButton("✕", self)
        self.btn_pin = QtWidgets.QPushButton("", self)
        self.btn_pin.setIcon(make_pin_icon(self._pinned))
        self.btn_pin.setIconSize(QtCore.QSize(14, 14))
        for b in (self.btn_min, self.btn_close, self.btn_pin):
            b.setStyleSheet(style)
            b.resize(18, 18)
            b.hide()
        self.btn_min.clicked.connect(self.hide_to_tray)
        self.btn_close.clicked.connect(self.quit_app)
        self.btn_pin.clicked.connect(self.toggle_pin)
        self._place_buttons()

    def _place_buttons(self):
        if not hasattr(self, "btn_close"):
            return
        w = self.width()
        self.btn_close.move(w - 22, 4)
        self.btn_min.move(w - 44, 4)
        if hasattr(self, "btn_pin"):
            self.btn_pin.move(w - 66, 4)

    def resizeEvent(self, e):
        self._place_buttons()

    def hideEvent(self, e):
        """隐藏到托盘：停掉 60Hz 重绘定时器并暂停音频 FFT，CPU 接近归零。"""
        if hasattr(self, "timer"):
            self.timer.stop()
        if hasattr(self, "audio"):
            self.audio.set_active(False)
        if hasattr(self, "media"):
            self.media.set_active(False)
        super().hideEvent(e)

    def showEvent(self, e):
        """从托盘恢复：重启重绘定时器并恢复音频处理。"""
        if hasattr(self, "timer") and not self.timer.isActive():
            self.timer.start(16)
        if hasattr(self, "audio"):
            self.audio.set_active(True)
        if hasattr(self, "media"):
            self.media.set_active(True)
        super().showEvent(e)

    def enterEvent(self, e):
        if hasattr(self, "btn_min"):
            self.btn_min.show()
            self.btn_close.show()
            self.btn_pin.show()

    def leaveEvent(self, e):
        if hasattr(self, "btn_min"):
            self.btn_min.hide()
            self.btn_close.hide()
            self.btn_pin.hide()

    def _update_pin_icon(self):
        """刷新 pin 按钮图标以反映当前固定状态。"""
        if hasattr(self, "btn_pin"):
            self.btn_pin.setIcon(make_pin_icon(self._pinned))

    def toggle_pin(self):
        """切换窗口置顶固定状态（不修改 display_mode 配置）。"""
        self._pinned = not self._pinned
        self._update_pin_icon()
        flags = self.windowFlags()
        if self._pinned:
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~QtCore.Qt.WindowType.WindowStaysOnTopHint
        # Qt 在 Windows 上更改 window flags 会隐藏窗口，需手动重新显示
        self.setWindowFlags(flags)
        self.show()
        if not self._pinned and cfg["display_mode"] == "desktop":
            self.lower()

    def _make_tray(self):
        icon = self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_MediaVolume)
        self.tray = QtWidgets.QSystemTrayIcon(icon, self)
        menu = QtWidgets.QMenu()
        # 保存 action 引用，语言切换时只更新文字，不重建菜单、不重连信号
        self._act_toggle = menu.addAction("")
        self._act_toggle.triggered.connect(self.toggle_visible)
        self._act_settings = menu.addAction("")
        self._act_settings.triggered.connect(self.open_settings)
        self._act_quit = menu.addAction("")
        self._act_quit.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self._retranslate_tray()
        self.tray.show()

    def _retranslate_tray(self):
        """刷新托盘 Tooltip 与菜单文字。"""
        self.tray.setToolTip(tr("app_name"))
        self._act_toggle.setText(tr("tray_toggle"))
        self._act_settings.setText(tr("tray_settings"))
        self._act_quit.setText(tr("tray_quit"))

    def retranslate_ui(self):
        """语言切换时刷新主窗口相关的所有可见文字（托盘等）。"""
        if hasattr(self, "tray"):
            self._retranslate_tray()

    def _tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visible()

    def hide_to_tray(self):
        self.hide()
        self.tray.showMessage(
            tr("tray_min_title"), tr("tray_min_msg"),
            QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2000)

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if cfg["display_mode"] == "desktop":
                self.lower()

    def rebuild_audio(self):
        self.audio.stop()
        self.audio.wait(500)
        self.audio = AudioThread(cfg["num_bars"])
        self.audio.start()

    def apply_color_mode(self):
        if cfg["color_mode"] == "fixed":
            self.color = QtGui.QColor(*cfg["fixed_color"])

    def on_color(self, r, g, b):
        if cfg["color_mode"] == "album":
            self.color = QtGui.QColor(r, g, b)
            self._dirty = True

    def on_title(self, text):
        self.song_title = text
        self._dirty = True

    def _tick(self):
        """仅在画面确有变化时重绘：静音或音柱几乎不动时跳过，降低 CPU。"""
        bars = self.audio.smoothed
        if (self._dirty or self._last_bars is None
                or self._last_bars.shape != bars.shape
                or np.max(np.abs(bars - self._last_bars)) > 0.002):
            self._last_bars = bars.copy()
            self._dirty = False
            self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 1))
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        src = self.audio.smoothed
        n = len(src)
        c = self.color
        use_grad = cfg["gradient"]

        # ---- 像素对齐布局：修复音柱粗细/间隙不均 ----
        # 柱距 = 窗口宽/柱数 通常不是整数（如 800/155≈5.16px），若逐根对齐
        # 取整，±0.5px 的残差会让柱宽或间隙在 floor/ceil 间跳动：此前表现
        # 为粗细不一（高 DPI 缩放下更明显），柱宽统一后又表现为部分间隙
        # 稍宽。根治办法是让柱距本身取整成统一整数步长——柱距、柱宽、
        # 间隙三者全部恒定，取整残差改为通过微调显示柱数吸收（对音频
        # 数据插值，柱数变化仅±几根，肉眼不可辨）。
        # 布局仅在窗口尺寸 / 音柱数 / 间距 / 缩放比变化时重算一次。
        dpr = self.devicePixelRatioF() or 1.0
        key = (w, h, n, cfg["bar_gap"], cfg["min_bar"], dpr)
        if key != self._layout_key:
            self._layout_key = key
            W = w * dpr
            step = max(1, int(W / n + 0.5))           # 统一柱距（物理像素）
            # 间隙向上取整并保证柱宽 ≥1 物理像素（设置值大于柱距时收敛到 1px 间隙）
            gap_p = min(int(cfg["bar_gap"] * dpr + 0.5), step - 1)
            self._step_p = step
            self._bar_w_p = step - gap_p
            # 显示柱数取「恰好铺满窗口」的最大值，右缘富余不足一个柱距
            self._n_disp = max(1, int((W - self._bar_w_p) // step) + 1)
            self._src_xs = np.arange(n, dtype=np.float64)
            self._disp_xs = (np.linspace(0.0, n - 1.0, self._n_disp)
                             if self._n_disp != n else None)
            self._area_p = max(1, int((h - cfg["title_area"]) * dpr + 0.5))
            self._min_h_p = max(1, int(cfg["min_bar"] * dpr + 0.5))

        bars = (src if self._disp_xs is None
                else np.interp(self._disp_xs, self._src_xs, src))

        # 颜色不变时复用缓存的 QColor，避免每帧为每根柱子重复构造对象
        rgb = (c.red(), c.green(), c.blue())
        if rgb != self._cached_rgb:
            self._cached_rgb = rgb
            self._solid = QtGui.QColor(rgb[0], rgb[1], rgb[2], 230)
            self._grad_top = QtGui.QColor(rgb[0], rgb[1], rgb[2], 235)
            self._grad_bot = QtGui.QColor(rgb[0], rgb[1], rgb[2], 120)
            # 颜色不变时色标也不变，仅在此处更新一次复用的渐变对象
            self._grad.setColorAt(0.0, self._grad_top)
            self._grad.setColorAt(1.0, self._grad_bot)
        solid = self._solid
        grad = self._grad
        dpr_inv = 1.0 / dpr
        x_step = self._step_p * dpr_inv       # 柱距换回逻辑坐标，绘制时
        bar_w_l = self._bar_w_p * dpr_inv     # 精确映射回同一物理像素网格
        area_p = self._area_p
        min_h_p = self._min_h_p

        for i, v in enumerate(bars):
            x = i * x_step                    # 第 i 根柱子左边缘：i×统一柱距
            bar_h = max(min_h_p, int(v * area_p + 0.5))   # 高度也对齐物理像素
            y = (area_p - bar_h) * dpr_inv
            if use_grad:
                # 复用同一渐变对象，每根柱子只更新起止点，
                # 观感与每帧新建独立渐变完全一致，但零对象分配
                grad.setStart(0.0, y)
                grad.setFinalStop(0.0, area_p * dpr_inv)
                p.fillRect(QtCore.QRectF(x, y, bar_w_l, bar_h * dpr_inv), grad)
            else:
                p.fillRect(QtCore.QRectF(x, y, bar_w_l, bar_h * dpr_inv), solid)

        if cfg["show_title"] and self.song_title:
            p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
            p.setFont(self._title_font)
            fm = self._title_fm
            # 仅当歌名变化时才重算包围盒，其余帧复用缓存
            if self.song_title != self._title_cache_text:
                self._title_cache_text = self.song_title
                self._title_base_rect = fm.boundingRect(self.song_title)
            tx, ty = cfg["title_x"], cfg["title_y"]
            self._title_rect = QtCore.QRect(self._title_base_rect)
            self._title_rect.moveTopLeft(QtCore.QPoint(tx, ty - fm.ascent()))
            p.setPen(QtGui.QColor(0, 0, 0, 170))
            p.drawText(tx + 1, ty + 1, self.song_title)
            p.setPen(QtGui.QColor(255, 255, 255, 235))
            p.drawText(tx, ty, self.song_title)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            gp = e.globalPosition().toPoint()
            local = gp - self.frameGeometry().topLeft()
            if (cfg["show_title"] and self.song_title
                    and self._title_rect.adjusted(-6, -6, 6, 6).contains(local)):
                self._drag_title = True
                self._title_off = local - QtCore.QPoint(
                    cfg["title_x"], cfg["title_y"])
            else:
                self._drag_title = False
                self._drag_pos = gp - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if not (e.buttons() & QtCore.Qt.MouseButton.LeftButton):
            return
        gp = e.globalPosition().toPoint()
        if self._drag_title:
            local = gp - self.frameGeometry().topLeft()
            new = local - self._title_off
            cfg["title_x"] = max(0, min(self.width() - 10, new.x()))
            cfg["title_y"] = max(10, min(self.height(), new.y()))
            self._dirty = True         # 拖动标题时强制刷新，静音时也跟手
        elif self._drag_pos:
            self.move(gp - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if self._drag_title:
            cfg.save()
        else:
            cfg["win_x"] = self.x()
            cfg["win_y"] = self.y()
        self._drag_title = False

    def contextMenuEvent(self, e):
        menu = QtWidgets.QMenu(self)
        set_act = menu.addAction(tr("menu_settings"))
        quit_act = menu.addAction(tr("menu_quit"))
        chosen = menu.exec(e.globalPos())
        if chosen == set_act:
            self.open_settings()
        elif chosen == quit_act:
            self.quit_app()

    def open_settings(self):
        if self.settings_win is None:
            self.settings_win = SettingsDialog(self)
        self.settings_win.show()
        self.settings_win.raise_()
        self.settings_win.activateWindow()

    def quit_app(self):
        cfg.save()
        self.audio.stop()
        self.media.stop()
        if hasattr(self, "tray"):
            self.tray.hide()
        QtWidgets.QApplication.quit()