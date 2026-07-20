# -*- coding: utf-8 -*-
"""Windows 桌面音频可视化小组件 v9"""

import sys
import os
import io
import json
import warnings

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
import soundcard as sc

warnings.filterwarnings("ignore")

DEFAULTS = {
    "num_bars":     160,
    "bar_gap":      1,
    "min_bar":      2,
    "rise_speed":   0.90,
    "fall_speed":   0.15,
    "sensitivity":  1.15,
    "tilt":         4.0,
    "color_mode":   "album",
    "fixed_color":  [0, 200, 255],
    "display_mode": "desktop",   # desktop=停在桌面 / top=置顶 / normal=普通
    "show_title":   True,
    "gradient":     True,
    "title_x":      12,
    "title_y":      24,
    "title_area":   70,
    "win_w":        800,
    "win_h":        200,
    "win_x":        100,
    "win_y":        700,
}

SAMPLE_RATE = 48000
FFT_SIZE    = 4096
CHUNK       = 1024

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "settings.json")


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存设置失败:", e)


CFG = load_config()


class AudioThread(QtCore.QThread):
    def __init__(self, num_bars):
        super().__init__()
        self.num_bars = num_bars
        self.running = True
        self.smoothed = np.zeros(num_bars)
        self.freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
        self.bar_freqs = np.logspace(np.log10(45), np.log10(16000), num_bars)
        self.tilt_db = CFG.get("tilt", 4.0) * np.log2(self.bar_freqs / 1000.0)

    def run(self):
        try:
            spk = sc.default_speaker()
            loop = sc.get_microphone(str(spk.name), include_loopback=True)
        except Exception as e:
            print("无法打开音频回环设备:", e)
            return
        buffer = np.zeros(FFT_SIZE)
        window = np.hanning(FFT_SIZE)
        with loop.recorder(samplerate=SAMPLE_RATE, blocksize=CHUNK) as rec:
            while self.running:
                try:
                    data = rec.record(numframes=CHUNK)
                except Exception:
                    continue
                mono = data.mean(axis=1)
                n = len(mono)
                if n >= FFT_SIZE:
                    buffer[:] = mono[-FFT_SIZE:]
                else:
                    # 原地左移，避免 np.roll 每帧分配新数组
                    buffer[:-n] = buffer[n:]
                    buffer[-n:] = mono
                spec = np.abs(np.fft.rfft(buffer * window))
                vals = np.interp(self.bar_freqs, self.freqs, spec)
                vals = np.clip(vals / FFT_SIZE, 1e-6, None)
                db = 20 * np.log10(vals) + self.tilt_db
                norm = np.clip((db + 70) / 60.0 * CFG["sensitivity"], 0, 1)
                up = norm > self.smoothed
                rate = np.where(up, CFG["rise_speed"], CFG["fall_speed"])
                self.smoothed += (norm - self.smoothed) * rate

    def stop(self):
        self.running = False


class MediaThread(QtCore.QThread):
    color_ready = QtCore.pyqtSignal(int, int, int)
    title_ready = QtCore.pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        import asyncio
        # 一次性导入 winrt 模块，避免每秒轮询时重复 import
        from winrt.windows.media.control import \
            GlobalSystemMediaTransportControlsSessionManager as MM
        from winrt.windows.storage.streams import \
            Buffer, InputStreamOptions, DataReader
        self._MM = MM
        self._Buffer = Buffer
        self._InputStreamOptions = InputStreamOptions
        self._DataReader = DataReader

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.running:
            try:
                color, title = loop.run_until_complete(self._fetch())
                self.title_ready.emit(title)
                if color:
                    self.color_ready.emit(*color)
            except Exception as e:
                print("[媒体] 出错:", e)
            self.msleep(1000)

    async def _fetch(self):
        MM = self._MM
        Buffer = self._Buffer
        InputStreamOptions = self._InputStreamOptions
        DataReader = self._DataReader
        mgr = await MM.request_async()
        s = mgr.get_current_session()
        if s is None:
            return (None, "")
        props = await s.try_get_media_properties_async()
        title = props.title or ""
        artist = props.artist or ""
        text = f"{artist} — {title}" if artist else title

        color = None
        if CFG["color_mode"] == "album" and props.thumbnail is not None:
            try:
                stream = await props.thumbnail.open_read_async()
                buf = Buffer(stream.size)
                await stream.read_async(
                    buf, buf.capacity, InputStreamOptions.READ_AHEAD)
                reader = DataReader.from_buffer(buf)
                out = bytearray(buf.length)
                reader.read_bytes(out)
                data = bytes(out)
                if data:
                    from PIL import Image
                    img = (Image.open(io.BytesIO(data))
                           .convert("RGB").resize((50, 50)))
                    arr = np.asarray(img).reshape(-1, 3).astype(float) / 255.0
                    mx, mn = arr.max(1), arr.min(1)
                    sat = np.where(mx > 0, (mx - mn) / mx, 0)
                    mask = (sat > 0.3) & (mx > 0.3)
                    sel = arr[mask] if mask.sum() > 10 else arr
                    col = (sel.mean(0) * 255).astype(int)
                    color = tuple(int(x) for x in col)
            except Exception:
                pass
        return (color, text)

    def stop(self):
        self.running = False

class SettingsDialog(QtWidgets.QWidget):
    def __init__(self, viz):
        super().__init__()
        self.viz = viz
        self.setWindowTitle("音频可视化 - 设置")
        self.setFixedWidth(360)
        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        layout = QtWidgets.QVBoxLayout(self)

        self._slider(layout, "上升速度（越大越灵敏）", 1, 100,
                     int(CFG["rise_speed"] * 100), self.on_rise)
        self._slider(layout, "下落速度（越小越拖尾顺滑）", 1, 100,
                     int(CFG["fall_speed"] * 100), self.on_fall)
        self._slider(layout, "灵敏度", 20, 300,
                     int(CFG["sensitivity"] * 100), self.on_sens)
        self._slider(layout, "低频压制（越大低频越平）", 0, 100,
                     int(CFG["tilt"] * 10), self.on_tilt)
        self._slider(layout, "音柱数量（越多越细）", 32, 320,
                     CFG["num_bars"], self.on_bars)
        self._slider(layout, "音柱间隙", 0, 10,
                     CFG["bar_gap"], self.on_gap)

        layout.addSpacing(8)
        self.title_chk = QtWidgets.QCheckBox("显示歌曲名")
        self.title_chk.setChecked(CFG["show_title"])
        self.title_chk.stateChanged.connect(self.on_title_chk)
        layout.addWidget(self.title_chk)
        self.grad_chk = QtWidgets.QCheckBox("音柱使用渐变色（取消则为纯色）")
        self.grad_chk.setChecked(CFG["gradient"])
        self.grad_chk.stateChanged.connect(self.on_grad_chk)
        layout.addWidget(self.grad_chk)

        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(QtWidgets.QLabel("颜色："))
        self.mode_box = QtWidgets.QComboBox()
        self.mode_box.addItems(["跟随专辑封面", "固定颜色"])
        self.mode_box.setCurrentIndex(0 if CFG["color_mode"] == "album" else 1)
        self.mode_box.currentIndexChanged.connect(self.on_mode)
        crow.addWidget(self.mode_box, 1)
        pick_btn = QtWidgets.QPushButton("选颜色")
        pick_btn.clicked.connect(self.on_pick_color)
        crow.addWidget(pick_btn)
        layout.addLayout(crow)

        drow = QtWidgets.QHBoxLayout()
        drow.addWidget(QtWidgets.QLabel("显示："))
        self.disp_box = QtWidgets.QComboBox()
        self.disp_box.addItems(["停在桌面", "永远置顶", "普通窗口"])
        self.disp_box.setCurrentIndex(
            {"desktop": 0, "top": 1, "normal": 2}.get(CFG["display_mode"], 0))
        self.disp_box.currentIndexChanged.connect(self.on_disp)
        drow.addWidget(self.disp_box, 1)
        layout.addLayout(drow)

        note = QtWidgets.QLabel("切换显示模式后需重启程序才完全生效。")
        note.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note)

        layout.addSpacing(8)
        btn = QtWidgets.QPushButton("保存并关闭")
        btn.clicked.connect(self.save_and_close)
        layout.addWidget(btn)

    def _slider(self, layout, title, lo, hi, val, cb):
        layout.addWidget(QtWidgets.QLabel(title))
        s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.valueChanged.connect(cb)
        layout.addWidget(s)
        return s

    def on_rise(self, v): CFG["rise_speed"] = v / 100.0
    def on_fall(self, v): CFG["fall_speed"] = v / 100.0
    def on_sens(self, v): CFG["sensitivity"] = v / 100.0

    def on_tilt(self, v):
        CFG["tilt"] = v / 10.0
        self.viz.rebuild_audio()

    def on_bars(self, v):
        CFG["num_bars"] = v
        self.viz.rebuild_audio()

    def on_gap(self, v): CFG["bar_gap"] = v
    def on_title_chk(self, _): CFG["show_title"] = self.title_chk.isChecked()
    def on_grad_chk(self, _): CFG["gradient"] = self.grad_chk.isChecked()

    def on_mode(self, idx):
        CFG["color_mode"] = "album" if idx == 0 else "fixed"
        self.viz.apply_color_mode()

    def on_pick_color(self):
        c = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(*CFG["fixed_color"]), self, "选择音柱颜色")
        if c.isValid():
            CFG["fixed_color"] = [c.red(), c.green(), c.blue()]
            CFG["color_mode"] = "fixed"
            self.mode_box.setCurrentIndex(1)
            self.viz.apply_color_mode()

    def on_disp(self, idx):
        CFG["display_mode"] = ["desktop", "top", "normal"][idx]

    def save_and_close(self):
        save_config(CFG)
        self.close()


class Visualizer(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        flags = QtCore.Qt.WindowType.FramelessWindowHint
        if CFG["display_mode"] == "top":
            flags |= QtCore.Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(CFG["win_w"], CFG["win_h"] + CFG["title_area"])
        self.move(CFG["win_x"], CFG["win_y"])

        self.color = QtGui.QColor(*CFG["fixed_color"])
        self._cached_rgb = None          # 上次构建画刷用的 (r,g,b)
        self._grad_top = None            # 缓存的渐变顶部颜色
        self._grad_bot = None            # 缓存的渐变底部颜色
        self._solid = None               # 缓存的纯色
        self.song_title = ""
        self._drag_pos = None
        self._drag_title = False
        self._title_off = QtCore.QPoint()
        self._title_rect = QtCore.QRect()
        self.settings_win = None

        self.audio = AudioThread(CFG["num_bars"])
        self.media = MediaThread()
        self.media.color_ready.connect(self.on_color)
        self.media.title_ready.connect(self.on_title)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

        QtCore.QTimer.singleShot(200, self._start_workers)

    def _start_workers(self):
        self.audio.start()
        self.media.start()
        self._make_buttons()
        self._make_tray()
        self.apply_color_mode()
        # 停在桌面模式：启动时把窗口沉到最底层，不再动窗口父子关系
        if CFG["display_mode"] == "desktop":
            self.lower()

    def _make_buttons(self):
        style = ("QPushButton{background:rgba(0,0,0,110);color:white;"
                 "border:none;border-radius:9px;font-size:12px;}"
                 "QPushButton:hover{background:rgba(0,0,0,190);}")
        self.btn_min = QtWidgets.QPushButton("—", self)
        self.btn_close = QtWidgets.QPushButton("✕", self)
        for b in (self.btn_min, self.btn_close):
            b.setStyleSheet(style)
            b.resize(18, 18)
            b.hide()
        self.btn_min.clicked.connect(self.hide_to_tray)
        self.btn_close.clicked.connect(self.quit_app)
        self._place_buttons()

    def _place_buttons(self):
        if not hasattr(self, "btn_close"):
            return
        w = self.width()
        self.btn_close.move(w - 22, 4)
        self.btn_min.move(w - 44, 4)

    def resizeEvent(self, e):
        self._place_buttons()

    def enterEvent(self, e):
        if hasattr(self, "btn_min"):
            self.btn_min.show()
            self.btn_close.show()

    def leaveEvent(self, e):
        if hasattr(self, "btn_min"):
            self.btn_min.hide()
            self.btn_close.hide()

    def _make_tray(self):
        icon = self.style().standardIcon(
            QtWidgets.QStyle.StandardPixmap.SP_MediaVolume)
        self.tray = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray.setToolTip("音频可视化")
        menu = QtWidgets.QMenu()
        menu.addAction("显示 / 隐藏").triggered.connect(self.toggle_visible)
        menu.addAction("设置").triggered.connect(self.open_settings)
        menu.addAction("退出").triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_visible()

    def hide_to_tray(self):
        self.hide()
        self.tray.showMessage(
            "音频可视化", "已最小化到托盘，双击托盘图标恢复。",
            QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2000)

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            if CFG["display_mode"] == "desktop":
                self.lower()

    def rebuild_audio(self):
        self.audio.stop()
        self.audio.wait(500)
        self.audio = AudioThread(CFG["num_bars"])
        self.audio.start()

    def apply_color_mode(self):
        if CFG["color_mode"] == "fixed":
            self.color = QtGui.QColor(*CFG["fixed_color"])

    def on_color(self, r, g, b):
        if CFG["color_mode"] == "album":
            self.color = QtGui.QColor(r, g, b)

    def on_title(self, text):
        self.song_title = text

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 1))
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        bar_area = h - CFG["title_area"]
        bars = self.audio.smoothed
        n = len(bars)
        gap = CFG["bar_gap"]
        minb = CFG["min_bar"]
        c = self.color
        cell = w / n
        bar_w = max(1.0, cell - gap)   # 所有柱子完全相同的浮点宽度
        use_grad = CFG["gradient"]

        # 颜色不变时复用缓存的 QColor，避免每帧为每根柱子重复构造对象
        rgb = (c.red(), c.green(), c.blue())
        if rgb != self._cached_rgb:
            self._cached_rgb = rgb
            self._solid = QtGui.QColor(rgb[0], rgb[1], rgb[2], 230)
            self._grad_top = QtGui.QColor(rgb[0], rgb[1], rgb[2], 235)
            self._grad_bot = QtGui.QColor(rgb[0], rgb[1], rgb[2], 120)
        solid = self._solid
        grad_top = self._grad_top
        grad_bot = self._grad_bot

        for i, v in enumerate(bars):
            x = i * cell               # 浮点起点，不取整，不累积误差
            bar_h = max(float(minb), v * bar_area)
            y = bar_area - bar_h
            if use_grad:
                grad = QtGui.QLinearGradient(0, y, 0, bar_area)
                grad.setColorAt(0.0, grad_top)
                grad.setColorAt(1.0, grad_bot)
                p.fillRect(QtCore.QRectF(x, y, bar_w, bar_h), grad)
            else:
                p.fillRect(QtCore.QRectF(x, y, bar_w, bar_h), solid)

        if CFG["show_title"] and self.song_title:
            p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
            font = QtGui.QFont()
            font.setFamilies(["Georgia", "SimSun"])
            font.setPointSize(13)
            font.setItalic(True)
            p.setFont(font)
            tx, ty = CFG["title_x"], CFG["title_y"]
            fm = QtGui.QFontMetrics(font)
            self._title_rect = fm.boundingRect(self.song_title)
            self._title_rect.moveTopLeft(QtCore.QPoint(tx, ty - fm.ascent()))
            p.setPen(QtGui.QColor(0, 0, 0, 170))
            p.drawText(tx + 1, ty + 1, self.song_title)
            p.setPen(QtGui.QColor(255, 255, 255, 235))
            p.drawText(tx, ty, self.song_title)

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.LeftButton:
            gp = e.globalPosition().toPoint()
            local = gp - self.frameGeometry().topLeft()
            if (CFG["show_title"] and self.song_title
                    and self._title_rect.adjusted(-6, -6, 6, 6).contains(local)):
                self._drag_title = True
                self._title_off = local - QtCore.QPoint(
                    CFG["title_x"], CFG["title_y"])
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
            CFG["title_x"] = max(0, min(self.width() - 10, new.x()))
            CFG["title_y"] = max(10, min(self.height(), new.y()))
        elif self._drag_pos:
            self.move(gp - self._drag_pos)

    def mouseReleaseEvent(self, e):
        if self._drag_title:
            save_config(CFG)
        else:
            CFG["win_x"] = self.x()
            CFG["win_y"] = self.y()
        self._drag_title = False

    def contextMenuEvent(self, e):
        menu = QtWidgets.QMenu(self)
        set_act = menu.addAction("设置")
        quit_act = menu.addAction("退出")
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
        save_config(CFG)
        self.audio.stop()
        self.media.stop()
        if hasattr(self, "tray"):
            self.tray.hide()
        QtWidgets.QApplication.quit()


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = Visualizer()
    win.show()
    sys.exit(app.exec())