# -*- coding: utf-8 -*-
"""多语言支持。

所有用户可见字符串集中于此。新增语言只需在 ``TR`` 中添加对应区域码字典，
无需改动任何业务逻辑。统一使用标准区域码（如 zh_CN / en_US）。

``tr(key)`` 在运行时从共享配置实例 ``cfg`` 读取当前语言，因此语言切换
在保存配置后即时对整个界面生效——与原单文件版本行为一致。
"""

from __future__ import annotations

from PyQt6 import QtCore

from .config import cfg

TR: dict[str, dict[str, str]] = {
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


def tr(key: str) -> str:
    """根据当前语言返回对应文本；缺失时回退到英文，再回退到 key 本身。"""
    lang = cfg.get("language") or "en_US"
    table = TR.get(lang, TR["en_US"])
    return table.get(key) or TR["en_US"].get(key, key)


def detect_system_language() -> str:
    """检测系统语言：中文系统 → zh_CN，其余一律 → en_US。"""
    try:
        name = QtCore.QLocale.system().name()   # 形如 "zh_CN"、"en_US"
    except Exception:
        return "en_US"
    return "zh_CN" if name.startswith("zh") else "en_US"