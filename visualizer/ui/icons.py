# -*- coding: utf-8 -*-
"""用 QPainter 绘制的小图标。

从主窗口里抽出来，便于复用与独立调整。对应原单文件中
``Visualizer._make_pin_icon`` 静态方法，行为完全一致。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui


def make_pin_icon(pinned: bool) -> QtGui.QIcon:
    """绘制图钉图标，风格与关闭/最小化按钮一致。

    pinned=True 时实心高亮白色，False 时半透明轮廓。
    """
    pm = QtGui.QPixmap(18, 18)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    alpha = 235 if pinned else 145
    col = QtGui.QColor(255, 255, 255, alpha)
    pen = QtGui.QPen(col, 1.4, QtCore.Qt.PenStyle.SolidLine,
                     QtCore.Qt.PenCapStyle.RoundCap,
                     QtCore.Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    # 图钉帽：顶部横向椭圆（实心）
    p.setBrush(col)
    p.drawEllipse(QtCore.QRectF(3.5, 1.5, 11, 5.5))
    # 针杆：从帽底中心垂直向下
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawLine(QtCore.QPointF(9, 7.2), QtCore.QPointF(9, 14.5))
    # 针尖横线（图钉插底后外露的横挡）
    p.drawLine(QtCore.QPointF(6.0, 14.5), QtCore.QPointF(12.0, 14.5))
    p.end()
    return QtGui.QIcon(pm)