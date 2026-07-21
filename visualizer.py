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
    "num_bars":     126,
    "bar_gap":      5,
    "min_bar":      2,
    "rise_speed":   0.9,
    "fall_speed":   0.14,
    "sensitivity":  0.83,
    "tilt":         7.1,
    "smooth_sigma": 0.8,
    "color_mode":   "fixed",
    "fixed_color":  [255, 255, 255],
    "display_mode": "normal",   # desktop=停在桌面 / top=置顶 / normal=普通
    "show_title":   True,
    "gradient":     True,
    "title_x":      0,
    "title_y":      222,
    "title_area":   70,
    "win_w":        800,
    "win_h":        200,
    "win_x":        464,
    "win_y":        755,
    "language":     "",          # 空 = 首次启动，将自动检测系统语言
}

# ---------------------------------------------------------------------------
# 多语言（i18n）翻译表
# 所有用户可见字符串集中于此。新增语言只需在 TR 中添加对应区域码字典，
# 无需改动任何业务逻辑。统一使用标准区域码（如 zh_CN, en_US）。
# ---------------------------------------------------------------------------
TR = {
    "zh_CN": {
        "app_name":           "音频可视化",
        "settings_title":     "音频可视化 - 设置",
        "language_label":     "语言：",
        "rise_speed":         "上升速度（越大越灵敏）",
        "fall_speed":         "下落速度（越小越拖尾顺滑）",
        "sensitivity":        "灵敏度",
        "tilt":               "低频压制（越大低频越平）",
        "smooth":             "频谱平滑（越大相邻音柱越柔和）",
        "num_bars":           "音柱数量（越多越细）",
        "bar_gap":            "音柱间隙",
        "show_title":         "显示歌曲名",
        "gradient":           "音柱使用渐变色（取消则为纯色）",
        "color_label":        "颜色：",
        "color_album":        "跟随专辑封面",
        "color_fixed":        "固定颜色",
        "pick_color":         "选颜色",
        "display_label":      "显示：",
        "display_desktop":    "停在桌面",
        "display_top":        "永远置顶",
        "display_normal":     "普通窗口",
        "display_note":       "切换显示模式后需重启程序才完全生效。",
        "save_close":         "保存并关闭",
        "color_dialog_title": "选择音柱颜色",
        "tray_toggle":        "显示 / 隐藏",
        "tray_settings":      "设置",
        "tray_quit":          "退出",
        "tray_min_title":     "音频可视化",
        "tray_min_msg":       "已最小化到托盘，双击托盘图标恢复。",
        "menu_settings":      "设置",
        "menu_quit":          "退出",
    },
    "en_US": {
        "app_name":           "Audio Visualizer",
        "settings_title":     "Audio Visualizer - Settings",
        "language_label":     "Language:",
        "rise_speed":         "Rise Speed (higher = more responsive)",
        "fall_speed":         "Fall Speed (lower = smoother trailing)",
        "sensitivity":        "Sensitivity",
        "tilt":               "Bass Attenuation (higher = flatter bass)",
        "smooth":             "Spectrum Smoothing (higher = softer bars)",
        "num_bars":           "Number of Bars (more = finer)",
        "bar_gap":            "Bar Gap",
        "show_title":         "Show Song Title",
        "gradient":           "Gradient Bars (uncheck for solid color)",
        "color_label":        "Color:",
        "color_album":        "Follow Album Art",
        "color_fixed":        "Fixed Color",
        "pick_color":         "Pick Color",
        "display_label":      "Display:",
        "display_desktop":    "On Desktop",
        "display_top":        "Always On Top",
        "display_normal":     "Normal Window",
        "display_note":       "Restart required for the display mode change "
                              "to fully take effect.",
        "save_close":         "Save & Close",
        "color_dialog_title": "Choose Bar Color",
        "tray_toggle":        "Show / Hide",
        "tray_settings":      "Settings",
        "tray_quit":          "Quit",
        "tray_min_title":     "Audio Visualizer",
        "tray_min_msg":       "Minimized to tray. Double-click the tray "
                              "icon to restore.",
        "menu_settings":      "Settings",
        "menu_quit":          "Quit",
    },
}


def tr(key):
    """根据当前语言返回对应文本；缺失时回退到英文，再回退到 key 本身。"""
    lang = CFG.get("language") or "en_US"
    table = TR.get(lang, TR["en_US"])
    return table.get(key) or TR["en_US"].get(key, key)


def detect_system_language():
    """检测系统语言：中文系统 → zh_CN，其余一律 → en_US。"""
    try:
        name = QtCore.QLocale.system().name()   # 形如 "zh_CN"、"en_US"
    except Exception:
        return "en_US"
    return "zh_CN" if name.startswith("zh") else "en_US"

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
    # 首次启动（无 language 设置）：自动检测系统语言并写回 settings.json；
    # 之后始终以用户保存的设置为准。
    if not cfg.get("language"):
        cfg["language"] = detect_system_language()
        save_config(cfg)
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
        self.sigma = CFG.get("smooth_sigma", 1.0)
        # 核与半径打包成单个元组，赋值是原子操作，避免与音频线程读写竞态
        self._k = None
        self._build_kernel()

    def _build_kernel(self):
        """按当前 sigma 预计算归一化高斯核；sigma<=0 时禁用平滑。"""
        sigma = self.sigma
        if sigma <= 0:
            self._k = None
            return
        radius = int(np.ceil(sigma * 3))
        x = np.arange(-radius, radius + 1)
        k = np.exp(-(x ** 2) / (2.0 * sigma ** 2))
        self._k = (k / k.sum(), radius)

    def set_sigma(self, sigma):
        """运行时调整平滑强度，只重建核，不重启线程。"""
        self.sigma = sigma
        self._build_kernel()

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
                # 频谱高斯平滑：对相邻音柱做一维高斯卷积，两端用 edge 填充，
                # 避免最左/最右音柱被拉低。kp 单次引用读取，天然规避线程竞态。
                kp = self._k
                if kp is not None:
                    kernel, pad = kp
                    padded = np.pad(norm, pad, mode="edge")
                    norm = np.convolve(padded, kernel, mode="valid")
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
        self.setFixedWidth(360)
        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        layout = QtWidgets.QVBoxLayout(self)
        # 保存需在语言切换时刷新文字的控件引用（key -> QLabel）
        self._slider_labels = {}

        # 语言选择：置于设置窗口顶部。选项文字固定为各自母语，不随界面语言变化
        lrow = QtWidgets.QHBoxLayout()
        self.lang_label = QtWidgets.QLabel()
        lrow.addWidget(self.lang_label)
        self.lang_box = QtWidgets.QComboBox()
        self.lang_box.addItem("简体中文", "zh_CN")
        self.lang_box.addItem("English", "en_US")
        li = self.lang_box.findData(CFG.get("language", "en_US"))
        self.lang_box.setCurrentIndex(li if li >= 0 else 0)
        self.lang_box.currentIndexChanged.connect(self.on_language)
        lrow.addWidget(self.lang_box, 1)
        layout.addLayout(lrow)

        self._slider(layout, "rise_speed", 1, 100,
                     int(CFG["rise_speed"] * 100), self.on_rise)
        self._slider(layout, "fall_speed", 1, 100,
                     int(CFG["fall_speed"] * 100), self.on_fall)
        self._slider(layout, "sensitivity", 20, 300,
                     int(CFG["sensitivity"] * 100), self.on_sens)
        self._slider(layout, "tilt", 0, 100,
                     int(CFG["tilt"] * 10), self.on_tilt)
        self._slider(layout, "smooth", 0, 50,
                     int(CFG["smooth_sigma"] * 10), self.on_smooth)
        self._slider(layout, "num_bars", 32, 320,
                     CFG["num_bars"], self.on_bars)
        self._slider(layout, "bar_gap", 0, 10,
                     CFG["bar_gap"], self.on_gap)

        layout.addSpacing(8)
        self.title_chk = QtWidgets.QCheckBox()
        self.title_chk.setChecked(CFG["show_title"])
        self.title_chk.stateChanged.connect(self.on_title_chk)
        layout.addWidget(self.title_chk)
        self.grad_chk = QtWidgets.QCheckBox()
        self.grad_chk.setChecked(CFG["gradient"])
        self.grad_chk.stateChanged.connect(self.on_grad_chk)
        layout.addWidget(self.grad_chk)

        crow = QtWidgets.QHBoxLayout()
        self.color_lbl = QtWidgets.QLabel()
        crow.addWidget(self.color_lbl)
        self.mode_box = QtWidgets.QComboBox()
        self.mode_box.addItems(["", ""])
        self.mode_box.setCurrentIndex(0 if CFG["color_mode"] == "album" else 1)
        self.mode_box.currentIndexChanged.connect(self.on_mode)
        crow.addWidget(self.mode_box, 1)
        self.pick_btn = QtWidgets.QPushButton()
        self.pick_btn.clicked.connect(self.on_pick_color)
        crow.addWidget(self.pick_btn)
        layout.addLayout(crow)

        drow = QtWidgets.QHBoxLayout()
        self.disp_lbl = QtWidgets.QLabel()
        drow.addWidget(self.disp_lbl)
        self.disp_box = QtWidgets.QComboBox()
        self.disp_box.addItems(["", "", ""])
        self.disp_box.setCurrentIndex(
            {"desktop": 0, "top": 1, "normal": 2}.get(CFG["display_mode"], 0))
        self.disp_box.currentIndexChanged.connect(self.on_disp)
        drow.addWidget(self.disp_box, 1)
        layout.addLayout(drow)

        self.note_lbl = QtWidgets.QLabel()
        self.note_lbl.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.note_lbl)

        layout.addSpacing(8)
        self.save_btn = QtWidgets.QPushButton()
        self.save_btn.clicked.connect(self.save_and_close)
        layout.addWidget(self.save_btn)

        # 初次填充所有文字
        self.retranslate_ui()

    def _slider(self, layout, key, lo, hi, val, cb):
        lbl = QtWidgets.QLabel()
        self._slider_labels[key] = lbl
        layout.addWidget(lbl)
        s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        s.valueChanged.connect(cb)
        layout.addWidget(s)
        return s

    def retranslate_ui(self):
        """按当前语言刷新所有文字，不重建任何控件、不重连任何信号。"""
        self.setWindowTitle(tr("settings_title"))
        self.lang_label.setText(tr("language_label"))
        for key, lbl in self._slider_labels.items():
            lbl.setText(tr(key))
        self.title_chk.setText(tr("show_title"))
        self.grad_chk.setText(tr("gradient"))
        self.color_lbl.setText(tr("color_label"))
        self.mode_box.setItemText(0, tr("color_album"))
        self.mode_box.setItemText(1, tr("color_fixed"))
        self.pick_btn.setText(tr("pick_color"))
        self.disp_lbl.setText(tr("display_label"))
        self.disp_box.setItemText(0, tr("display_desktop"))
        self.disp_box.setItemText(1, tr("display_top"))
        self.disp_box.setItemText(2, tr("display_normal"))
        self.note_lbl.setText(tr("display_note"))
        self.save_btn.setText(tr("save_close"))

    def on_language(self, _):
        """语言切换：更新配置并原地刷新所有界面文字。"""
        lang = self.lang_box.currentData()
        if not lang or lang == CFG.get("language"):
            return
        CFG["language"] = lang
        save_config(CFG)
        self.retranslate_ui()
        self.viz.retranslate_ui()

    def on_rise(self, v): CFG["rise_speed"] = v / 100.0
    def on_fall(self, v): CFG["fall_speed"] = v / 100.0
    def on_sens(self, v): CFG["sensitivity"] = v / 100.0

    def on_tilt(self, v):
        CFG["tilt"] = v / 10.0
        self.viz.rebuild_audio()

    def on_smooth(self, v):
        CFG["smooth_sigma"] = v / 10.0
        self.viz.audio.set_sigma(CFG["smooth_sigma"])

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
            QtGui.QColor(*CFG["fixed_color"]), self, tr("color_dialog_title"))
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
            # 颜色不变时色标也不变，仅在此处更新一次复用的渐变对象
            self._grad.setColorAt(0.0, self._grad_top)
            self._grad.setColorAt(1.0, self._grad_bot)
        solid = self._solid
        grad = self._grad
        bar_area_f = float(bar_area)

        for i, v in enumerate(bars):
            x = i * cell               # 浮点起点，不取整，不累积误差
            bar_h = max(float(minb), v * bar_area)
            y = bar_area - bar_h
            if use_grad:
                # 复用同一渐变对象，每根柱子只更新起止点，
                # 观感与每帧新建独立渐变完全一致，但零对象分配
                grad.setStart(0.0, y)
                grad.setFinalStop(0.0, bar_area_f)
                p.fillRect(QtCore.QRectF(x, y, bar_w, bar_h), grad)
            else:
                p.fillRect(QtCore.QRectF(x, y, bar_w, bar_h), solid)

        if CFG["show_title"] and self.song_title:
            p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
            p.setFont(self._title_font)
            fm = self._title_fm
            # 仅当歌名变化时才重算包围盒，其余帧复用缓存
            if self.song_title != self._title_cache_text:
                self._title_cache_text = self.song_title
                self._title_base_rect = fm.boundingRect(self.song_title)
            tx, ty = CFG["title_x"], CFG["title_y"]
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
            self._dirty = True         # 拖动标题时强制刷新，静音时也跟手
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