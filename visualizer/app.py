# -*- coding: utf-8 -*-
"""应用装配：配置加载 → QApplication → 主窗口 → 事件循环。

对应原单文件中模块顶层的 ``CFG = load_config()`` 与末尾的
``if __name__ == "__main__"`` 块，逻辑等价，仅做封装。
"""

from __future__ import annotations

import sys

from PyQt6 import QtWidgets

from .config import cfg
from .i18n import detect_system_language
from .ui.main_window import Visualizer


def load_config_with_detect() -> None:
    """加载配置；首次启动（无 language 设置）自动检测系统语言并写回。

    与原单文件 ``load_config()`` 行为一致：检测后立即 save，使后续启动
    始终以用户保存的设置为准。
    """
    cfg.load()
    if not cfg.get("language"):
        cfg["language"] = detect_system_language()
        cfg.save()


def main() -> int:
    load_config_with_detect()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = Visualizer()
    win.show()
    return sys.exit(app.exec())


if __name__ == "__main__":
    main()