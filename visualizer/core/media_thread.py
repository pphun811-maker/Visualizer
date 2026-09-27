# -*- coding: utf-8 -*-
"""系统媒体信息轮询线程。

对应原单文件中的 ``MediaThread`` 类，逻辑逐字保留，仅做一处结构性改动：
不再引用模块级 ``CFG`` 全局变量，改为从 ``visualizer.config`` 导入
共享实例 ``cfg``。两者是同一个对象，线程读写语义不变。
"""

from __future__ import annotations

import io

import numpy as np
from PyQt6 import QtCore

from ..config import cfg


class MediaThread(QtCore.QThread):
    color_ready = QtCore.pyqtSignal(int, int, int)
    title_ready = QtCore.pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.running = True
        self.active = True          # 隐藏到托盘时置 False，放宽轮询间隔
        self._last_title = None     # 上次已 emit 的歌名，用于去重
        self._art_title = None      # 上次成功解码封面对应的歌名
        self._art_mode = None       # 上次解码时的颜色模式

    def set_active(self, active: bool) -> None:
        """窗口显示/隐藏时切换，隐藏时降低轮询频率。"""
        self.active = active

    def run(self) -> None:
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
                # 歌名未变则不 emit，避免每秒把窗口标记为 dirty 触发无谓重绘
                if title != self._last_title:
                    self._last_title = title
                    self.title_ready.emit(title)
                if color:
                    self.color_ready.emit(*color)
            except Exception as e:
                print("[媒体] 出错:", e)
            # 显示时 1s 轮询保证跟手，隐藏到托盘时放宽到 3s 进一步省电
            self.msleep(1000 if self.active else 3000)

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
        mode = cfg["color_mode"]
        # 仅在 album 模式、且换歌或刚切到 album 模式时才解码封面，
        # 避免同一首歌每秒用 PIL 重复解码同一张图，显著降低静默 CPU
        need_decode = (mode == "album" and props.thumbnail is not None
                       and (text != self._art_title or self._art_mode != "album"))
        if mode != "album":
            self._art_mode = mode
        if need_decode:
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
                # 记录本次解码对应的歌名与模式，供下一轮去重判断
                self._art_title = text
                self._art_mode = "album"
            except Exception:
                pass
        return (color, text)

    def stop(self) -> None:
        self.running = False