# -*- coding: utf-8 -*-
"""音频采集 + FFT 线程。

对应原单文件中的 ``AudioThread`` 类，逻辑逐字保留，仅做两处结构性改动：

1. 不再引用模块级 ``CFG`` 全局变量，改为从 ``visualizer.config`` 导入
   共享实例 ``cfg``。两者是同一个对象，线程读写语义不变。
2. 音频常量从 ``visualizer.constants`` 导入。
"""

from __future__ import annotations

import numpy as np
import soundcard as sc
from PyQt6 import QtCore

from ..config import cfg
from ..constants import CHUNK, FFT_SIZE, SAMPLE_RATE


class AudioThread(QtCore.QThread):
    def __init__(self, num_bars: int) -> None:
        super().__init__()
        self.num_bars = num_bars
        self.running = True
        self.active = True          # 隐藏到托盘时置 False，暂停 FFT 处理
        self.smoothed = np.zeros(num_bars)
        self.freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
        self.bar_freqs = np.logspace(np.log10(45), np.log10(16000), num_bars)
        self.tilt_db = cfg.get("tilt", 4.0) * np.log2(self.bar_freqs / 1000.0)
        self.sigma = cfg.get("smooth_sigma", 1.0)
        # 核与半径打包成单个元组，赋值是原子操作，避免与音频线程读写竞态
        self._k = None
        self._build_kernel()

    def _build_kernel(self) -> None:
        """按当前 sigma 预计算归一化高斯核；sigma<=0 时禁用平滑。"""
        sigma = self.sigma
        if sigma <= 0:
            self._k = None
            return
        radius = int(np.ceil(sigma * 3))
        x = np.arange(-radius, radius + 1)
        k = np.exp(-(x ** 2) / (2.0 * sigma ** 2))
        self._k = (k / k.sum(), radius)

    def set_sigma(self, sigma: float) -> None:
        """运行时调整平滑强度，只重建核，不重启线程。"""
        self.sigma = sigma
        self._build_kernel()

    def set_active(self, active: bool) -> None:
        """窗口显示/隐藏时切换。隐藏时暂停整套 FFT 流水线以省 CPU。"""
        self.active = active

    def run(self) -> None:
        try:
            spk = sc.default_speaker()
            loop = sc.get_microphone(str(spk.name), include_loopback=True)
        except Exception as e:
            print("无法打开音频回环设备:", e)
            return
        buffer = np.zeros(FFT_SIZE)
        window = np.hanning(FFT_SIZE)
        SILENCE = 1e-4              # 峰值低于此值判定为静音
        with loop.recorder(samplerate=SAMPLE_RATE, blocksize=CHUNK) as rec:
            while self.running:
                try:
                    data = rec.record(numframes=CHUNK)
                except Exception:
                    continue
                # 隐藏到托盘：丢弃数据、音柱归零，跳过一切 FFT 计算
                if not self.active:
                    if self.smoothed.any():
                        self.smoothed[:] = 0.0
                    continue
                mono = data.mean(axis=1)
                # 静音检测：无声时跳过整套 FFT 流水线，仅让音柱自然衰减到 0，
                # 完全归零后连衰减都省掉，CPU 几乎回落到空转水平
                if np.abs(mono).max() < SILENCE:
                    if self.smoothed.max() > 0.001:
                        self.smoothed *= (1.0 - cfg["fall_speed"])
                    else:
                        self.smoothed[:] = 0.0
                    continue
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
                norm = np.clip((db + 70) / 60.0 * cfg["sensitivity"], 0, 1)
                # 频谱高斯平滑：对相邻音柱做一维高斯卷积，两端用 edge 填充，
                # 避免最左/最右音柱被拉低。kp 单次引用读取，天然规避线程竞态。
                kp = self._k
                if kp is not None:
                    kernel, pad = kp
                    padded = np.pad(norm, pad, mode="edge")
                    norm = np.convolve(padded, kernel, mode="valid")
                up = norm > self.smoothed
                rate = np.where(up, cfg["rise_speed"], cfg["fall_speed"])
                self.smoothed += (norm - self.smoothed) * rate

    def stop(self) -> None:
        self.running = False