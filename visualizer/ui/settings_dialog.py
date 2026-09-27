# -*- coding: utf-8 -*-
"""设置对话框。

对应原单文件中的 ``SettingsDialog`` 类，逻辑逐字保留，仅做三处改动：

1. 不再引用模块级 ``CFG`` 全局变量，改为从 ``visualizer.config`` 导入
   共享实例 ``cfg``；``save_config(CFG)`` 改为 ``cfg.save()``。
2. ``tr`` 从 ``visualizer.i18n`` 导入。
3. 不再持有主窗口的强引用，主窗口实例通过构造参数 ``viz`` 注入（与原版
   签名一致，``viz`` 仍是 ``Visualizer`` 实例）。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from ..config import cfg
from ..i18n import tr


class SettingsDialog(QtWidgets.QWidget):
    def __init__(self, viz) -> None:
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
        li = self.lang_box.findData(cfg.get("language", "en_US"))
        self.lang_box.setCurrentIndex(li if li >= 0 else 0)
        self.lang_box.currentIndexChanged.connect(self.on_language)
        lrow.addWidget(self.lang_box, 1)
        layout.addLayout(lrow)

        self._slider(layout, "rise_speed", 1, 100,
                     int(cfg["rise_speed"] * 100), self.on_rise)
        self._slider(layout, "fall_speed", 1, 100,
                     int(cfg["fall_speed"] * 100), self.on_fall)
        self._slider(layout, "sensitivity", 20, 300,
                     int(cfg["sensitivity"] * 100), self.on_sens)
        self._slider(layout, "tilt", 0, 100,
                     int(cfg["tilt"] * 10), self.on_tilt)
        self._slider(layout, "smooth", 0, 50,
                     int(cfg["smooth_sigma"] * 10), self.on_smooth)
        self._slider(layout, "num_bars", 32, 320,
                     cfg["num_bars"], self.on_bars)
        self._slider(layout, "bar_gap", 0, 10,
                     cfg["bar_gap"], self.on_gap)

        layout.addSpacing(8)
        self.title_chk = QtWidgets.QCheckBox()
        self.title_chk.setChecked(cfg["show_title"])
        self.title_chk.stateChanged.connect(self.on_title_chk)
        layout.addWidget(self.title_chk)
        self.grad_chk = QtWidgets.QCheckBox()
        self.grad_chk.setChecked(cfg["gradient"])
        self.grad_chk.stateChanged.connect(self.on_grad_chk)
        layout.addWidget(self.grad_chk)

        crow = QtWidgets.QHBoxLayout()
        self.color_lbl = QtWidgets.QLabel()
        crow.addWidget(self.color_lbl)
        self.mode_box = QtWidgets.QComboBox()
        self.mode_box.addItems(["", ""])
        self.mode_box.setCurrentIndex(0 if cfg["color_mode"] == "album" else 1)
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
            {"desktop": 0, "top": 1, "normal": 2}.get(cfg["display_mode"], 0))
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
        if not lang or lang == cfg.get("language"):
            return
        cfg["language"] = lang
        cfg.save()
        self.retranslate_ui()
        self.viz.retranslate_ui()

    def on_rise(self, v): cfg["rise_speed"] = v / 100.0
    def on_fall(self, v): cfg["fall_speed"] = v / 100.0
    def on_sens(self, v): cfg["sensitivity"] = v / 100.0

    def on_tilt(self, v):
        cfg["tilt"] = v / 10.0
        self.viz.rebuild_audio()

    def on_smooth(self, v):
        cfg["smooth_sigma"] = v / 10.0
        self.viz.audio.set_sigma(cfg["smooth_sigma"])

    def on_bars(self, v):
        cfg["num_bars"] = v
        self.viz.rebuild_audio()

    def on_gap(self, v): cfg["bar_gap"] = v
    def on_title_chk(self, _): cfg["show_title"] = self.title_chk.isChecked()
    def on_grad_chk(self, _): cfg["gradient"] = self.grad_chk.isChecked()

    def on_mode(self, idx):
        cfg["color_mode"] = "album" if idx == 0 else "fixed"
        self.viz.apply_color_mode()

    def on_pick_color(self):
        c = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(*cfg["fixed_color"]), self, tr("color_dialog_title"))
        if c.isValid():
            cfg["fixed_color"] = [c.red(), c.green(), c.blue()]
            cfg["color_mode"] = "fixed"
            self.mode_box.setCurrentIndex(1)
            self.viz.apply_color_mode()

    def on_disp(self, idx):
        cfg["display_mode"] = ["desktop", "top", "normal"][idx]

    def save_and_close(self):
        cfg.save()
        self.close()