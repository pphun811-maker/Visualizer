# -*- coding: utf-8 -*-
"""配置管理。

设计要点（与原单文件保持一致）：

* 单一共享实例 ``cfg``，由 UI 和两个后台线程并发读写。
  这是原始版本刻意采用的"活引用"语义——设置对话框拖滑块会实时改
  ``cfg["tilt"]``，而音频线程每个循环都在读 ``cfg["rise_speed"]`` 等。
  重构不改变这一语义，只是让配置有了归属和封装，不再裸用全局 dict。
* ``Config`` 行为类似字典（实现 ``__getitem__`` / ``__setitem__`` /
  ``get``），同时提供 ``load`` / ``save``。
* 配置文件路径在打包与开发环境下都解析到 exe/脚本所在目录的
  ``settings.json``，与原版一致。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

DEFAULTS: dict[str, Any] = {
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


def _base_dir() -> str:
    """打包环境用 exe 所在目录；开发环境用脚本所在目录。

    注意：本模块位于 ``visualizer/`` 包内，开发环境下 ``__file__`` 指向
    ``visualizer/config.py``，因此配置会落在源码根目录的 ``settings.json``，
    与原单文件 ``visualizer.py`` 同目录的行为一致。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 配置文件路径在导入时确定一次即可；与原版逻辑一致。
CONFIG_PATH = os.path.join(_base_dir(), "settings.json")


class Config:
    """字典式访问的共享配置，封装 load/save。

    保留 ``__getitem__`` / ``__setitem__`` / ``get`` 是为了让原单文件里
    ``CFG["tilt"] = ...`` 这类直接赋值的写法在重构后逐字不变地工作，
    同时维持 UI 与后台线程之间实时生效的"活引用"语义。
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(DEFAULTS)

    # --- 字典式访问 -------------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, other: dict[str, Any]) -> None:
        self._data.update(other)

    # --- 持久化 -----------------------------------------------------------
    def load(self) -> None:
        """从 settings.json 读取并合并到默认值上；失败时保持默认。"""
        self._data = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self._data.update(json.load(f))
        except Exception:
            pass

    def save(self) -> None:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存设置失败:", e)


# 单一共享实例。整个应用通过 ``from visualizer.config import cfg`` 拿到同一份。
cfg = Config()