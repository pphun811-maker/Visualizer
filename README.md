English | [简体中文](README.zh-CN.md)

# Visualizer

A small desktop audio spectrum widget for Windows, written in Python with PyQt6. It captures whatever your PC is currently playing (speaker loopback), runs an FFT on it, and draws the result as a row of frequency bars in a frameless, translucent window sitting on the desktop. If a player exposes its state through Windows' media controls, the widget can also show the track title and tint the bars using the album art.

There is no window chrome — the widget is dragged directly with the mouse and lives in the system tray.

## What it does

**Audio capture and spectrum**

- Captures the default output device's loopback stream with [soundcard](https://github.com/bastibe/soundcard) (WASAPI loopback) at 48 kHz, 1024 frames per read.
- Feeds a rolling 4096-sample buffer through a Hann window and takes a real FFT (`numpy.fft.rfft`).
- Interpolates the spectrum onto log-spaced bins between 45 Hz and 16 kHz, so each bar covers roughly an equal musical interval instead of an equal number of hertz.
- Converts to dB, applies the user's bass attenuation (`tilt * log2(f/1000)`), normalizes to 0–1, then optionally convolves neighbouring bars with a Gaussian kernel so the outline looks softer.
- Bars rise and fall at different rates (`rise_speed` / `fall_speed`), so they snap up on a transient and decay smoothly afterwards.
- Bars are laid out on an integer device-pixel grid (uniform bar pitch, width and gap), so bar thickness and spacing stay even at any DPI scaling or window width.

**Media information**

- Polls Windows' `GlobalSystemMediaTransportControlsSessionManager` through the `winrt` bindings once per second while visible (every 3 seconds while hidden) and draws `Artist — Title` under the bars.
- In **Follow Album Art** mode it decodes the current track's thumbnail with Pillow, resizes it to 50×50, and averages the pixels that are reasonably saturated and bright (saturation > 0.3, value > 0.3, falling back to the whole image if too few qualify). The result becomes the bar colour. Decoding only happens when the track changes, not on every poll.

**Window and interaction**

- Frameless and translucent; size and position are restored from `settings.json`. Drag anywhere to move the window, drag the title text to position the title independently (saved back to the settings file).
- Hovering reveals three buttons: minimize to tray, pin (toggle always-on-top), and close. Right-click opens a Settings / Quit menu.
- Minimizing hides it to the tray; double-click the tray icon to bring it back. While hidden, the repaint timer stops, the FFT pipeline pauses and media polling drops to 3 s, so a hidden widget costs close to nothing.

**Settings dialog** (right-click → Settings)

- Sliders: rise speed, fall speed, sensitivity, bass attenuation, spectrum smoothing, bar count (32–320), bar gap (0–10). Most apply immediately; changing bar count or bass tilt restarts the audio thread.
- Toggles: show song title, and gradient bars (top alpha 235 → bottom 120; when off, a flat colour at alpha 230 is used).
- Colour: follow album art, or a fixed colour chosen with the standard colour picker.
- Display mode, and a 简体中文 / English switch. The first launch detects the language from your system locale and saves it.

## Display modes

| Setting | What it actually does |
| --- | --- |
| On Desktop | A plain frameless window that is `lower()`ed to the bottom of the Z-order on startup and whenever it is restored from the tray. It is *not* attached to the desktop shell, so any window covering that area of the screen will still hide it. |
| Always On Top | Built with `WindowStaysOnTopHint`; the pin button can toggle it at runtime without a restart. |
| Normal Window | Plain window with normal Z-order. |

Switching the display mode in the settings dialog requires a restart to fully take effect.

## Requirements

- Windows 10/11. The media-info side uses Windows Runtime APIs and audio capture relies on WASAPI loopback, so the project is Windows-only in practice — there is no Linux/macOS code path.
- Python 3 plus the packages in `requirements.txt`: PyQt6, soundcard, numpy, Pillow and several `winrt-*` packages.

## Notes and limitations

- Rendering is done with `QPainter` on the CPU, driven by a ~60 Hz timer. The timer only triggers a repaint when the bars have actually moved (delta > 0.002) or something dirty changed, and the FFT is skipped entirely during silence. It is not a game overlay and injects nothing into other processes; if you still want it fully out of the way, minimize it to the tray — that stops the work outright.
- There is no audio device picker: the widget always uses the default speaker as reported by `soundcard`. If no loopback device can be opened, the thread prints an error and the bars stay flat.
- The repository contains source only — no installer and no prebuilt binary. Use the build command below to produce one.
- No test suite and no CI; the project is a personal desktop toy.

Project structure (refactored from a single visualizer.py into a package):

    visualizer/
      __main__.py           entry point (python -m visualizer)
      app.py                QApplication bootstrap
      config.py             settings load/save (settings.json)
      constants.py          shared geometry / bar constants
      i18n.py               translations and system language detection
      core/
        audio_thread.py     WASAPI loopback capture + FFT
        media_thread.py     Windows media session polling
      ui/
        main_window.py      frameless transparent overlay widget
        settings_dialog.py  settings panel
        icons.py            button icon rendering
    Visualizer.spec         PyInstaller build recipe
    requirements.txt        runtime dependencies

Running from source:

    pip install -r requirements.txt
    python -m visualizer

Building a standalone bundle:

    pyinstaller Visualizer.spec

Settings are stored in settings.json next to the script (or next to the .exe
when frozen); it is created on first run and is not tracked by git.

For any feedback or suggestions, please contact me via email at pengyuc14@gmail.com.
