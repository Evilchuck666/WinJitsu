# 🥋 WinJitsu

![Platform](https://img.shields.io/badge/platform-GNU%2FLinux%20%28X11%29-blue)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![Requires](https://img.shields.io/badge/requires-xdotool%2C%20python--xlib-blue)
[![License](https://img.shields.io/badge/license-GPLv3-green)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/Evilchuck666/WinJitsu?label=download&sort=semver)](https://github.com/Evilchuck666/WinJitsu/releases/latest)
[![Build and tests](https://github.com/Evilchuck666/WinJitsu/actions/workflows/release.yaml/badge.svg?branch=main)](https://github.com/Evilchuck666/WinJitsu/actions/workflows/release.yaml)

**Snap your windows into place, with smooth animations.**

WinJitsu is a slick, animated window management tool for Linux (X11).
It allows you to effortlessly snap your active windows to various positions
on your screen with smooth animations, making your workflow feel more organic and responsive. ✨

🌐 **Website:** https://evilchuck666.github.io/WinJitsu/

<!-- SCREENSHOTS:START -->
## 🎬 Demo

[![WinJitsu demo: a terminal snaps to halves, quarters, the center, fullscreen and the next monitor, with each action subtitled](site/assets/screenshots/winjitsu-demo-preview.webp)](https://evilchuck666.github.io/WinJitsu/assets/screenshots/winjitsu-demo.mp4)

Recorded on a two-monitor X11 desktop, with each action subtitled as it runs.
Click the preview to watch the full-resolution video ([MP4](site/assets/screenshots/winjitsu-demo.mp4), 48 s).

<!-- SCREENSHOTS:END -->

## ✨ Features

-   **Smooth Animations**: Windows glide to their new positions instead of just jumping there. 🌬️
-   **Grid Snapping**: Position windows easily to the North, South, East, West, corners, or center. 🧭
-   **Multi-Monitor Support**: Move windows between displays with ease. 🖥️ ➡️ 🖥️
-   **Fullscreen Toggling**: Smart fullscreen with configurable padding. ↔️
-   **Undo**: Every action can be undone, one step at a time, per window. 🔙
-   **Background Daemon**: A small daemon answers hotkeys instantly and collapses key-repeat bursts into one action. ⚡
-   **Config File**: Persist your preferences in `~/.config/winjitsu/config.ini`. ⚙️
-   **CLI Overrides**: Override config values when starting the daemon — no file editing needed. 🎛️

## 📥 Download

| Channel | Package |
| --- | --- |
| Arch Linux (AUR) | [winjitsu](https://aur.archlinux.org/packages/winjitsu) |
| PyPI | [WinJitsu](https://pypi.org/project/WinJitsu/) |
| GitHub release | [Wheel (v0.5.1)](https://github.com/Evilchuck666/WinJitsu/releases/download/v0.5.1/winjitsu-0.5.1-py3-none-any.whl) · [Source archive](https://github.com/Evilchuck666/WinJitsu/releases/download/v0.5.1/winjitsu-0.5.1.tar.gz) · [All downloads](https://github.com/Evilchuck666/WinJitsu/releases/latest) |

[Release notes](https://github.com/Evilchuck666/WinJitsu/releases/latest) · [SHA256SUMS.txt](https://github.com/Evilchuck666/WinJitsu/releases/latest/download/SHA256SUMS.txt)

## 🚀 Getting started

### 🏹 On Arch‑based systems

WinJitsu is available in the AUR. You can install it using your favorite AUR helper (e.g., `yay`):

```bash
yay -S winjitsu
```

### 🐍 From PyPI

```bash
pip install WinJitsu
```

`xdotool` still has to come from your distribution (see Requirements below).

### ▶️ First run

```bash
winjitsu --daemon   # start the daemon once per session
winjitsu E          # snap the active window to the right half
```

## 📋 Requirements

Make sure you have the following installed on your system:

-   Python 3.10+ 🐍
-   `xdotool` (for window manipulation)
-   `python-xlib` / `python3-xlib` (for screen detection via RandR)

### Installing Dependencies

### 🐧 Arch‑based distributions (Arch Linux, EndeavourOS, Manjaro, etc.)

```bash
sudo pacman -S python xdotool python-xlib
```

### 🐧 Debian‑based distributions (Debian, Ubuntu, Linux Mint, etc.)

```bash
sudo apt install python3 xdotool python3-xlib
```

### 🐧 Fedora‑based distributions (Fedora, CentOS, etc.)

```bash
sudo dnf install python3 xdotool python3-xlib
```

## 🎮 Usage

Run the command with an action argument to control the active window:

```bash
winjitsu [ACTION] [OPTIONS]
```

> ⚠️ **WinJitsu requires the daemon to be running.**
> Start it once with `winjitsu --daemon` before using any action.

### Available Actions

| Action | Description                            | Emoji |
|:-------|:---------------------------------------|:------|
| `N`    | Move to North (Top Half)               | ⬆️    |
| `S`    | Move to South (Bottom Half)            | ⬇️    |
| `E`    | Move to East (Right Half)              | ➡️    |
| `W`    | Move to West (Left Half)               | ⬅️    |
| `NE`   | Move to North-East                     | ↗️    |
| `NW`   | Move to North-West                     | ↖️    |
| `SE`   | Move to South-East                     | ↘️    |
| `SW`   | Move to South-West                     | ↙️    |
| `C`    | Center the window (keeps its size)     | 🎯    |
| `F`    | Fullscreen (minus `padding`)           | 🖥️   |
| `U`    | Undo the last action on the window     | 🔙    |
| `TF`   | Toggle fullscreen (leaving it undoes)  | 🔄    |
| `TD`   | Move to the next monitor               | 📺    |
| `CC`   | Clear the undo history                 | 🧹    |

**Undo** works per window: every action WinJitsu performs is stacked, and each `U` takes the window one step back, maximized again if it was. If you moved the window yourself since the last action, the first `U` puts it back where that action left it. The history is kept in `~/.cache/winjitsu/state.db` (respects `$XDG_CACHE_HOME`) and cleared whenever the daemon starts or you run `CC`.

### Binding keys

For the best experience, bind these commands to keyboard shortcuts in your window manager configuration
(e.g., i3, creating custom shortcuts in GNOME/KDE).

Example:
-   `Super + Up` -> `winjitsu N`
-   `Super + Right` -> `winjitsu E`

Happy tiling! 🎉

## 📚 Learn more

- [Technical guide](TECHNICAL_GUIDE.md): configuration file and options,
  daemon mode, and installing from a wheel or from source.

## ⚖️ License

WinJitsu is free software released under the **GNU General Public License v3.0** (GPL-3.0). See [LICENSE](LICENSE).
