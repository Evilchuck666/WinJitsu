# 🥋 WinJitsu

![Platform](https://img.shields.io/badge/platform-GNU%2FLinux%20%28X11%29-blue)
![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![Requires](https://img.shields.io/badge/requires-xdotool%2C%20python--xlib-blue)
[![License](https://img.shields.io/badge/license-GPLv3-green)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/Evilchuck666/WinJitsu?label=download&sort=semver)](https://github.com/Evilchuck666/WinJitsu/releases/latest)
[![Build and tests](https://github.com/Evilchuck666/WinJitsu/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/Evilchuck666/WinJitsu/actions/workflows/release.yml)

**WinJitsu** is a slick, animated window management tool for Linux (X11).
It allows you to effortlessly snap your active windows to various positions
on your screen with smooth animations, making your workflow feel more organic and responsive. ✨


---

## 🚀 Features

-   **Smooth Animations**: Windows glide to their new positions instead of just jumping there. 🌬️
-   **Grid Snapping**: Position windows easily to the North, South, East, West, corners, or center. 🧭
-   **Multi-Monitor Support**: Move windows between displays with ease. 🖥️ ➡️ 🖥️
-   **Fullscreen Toggling**: Smart fullscreen with configurable padding, and restore to each window's home position. ↔️
-   **Background Daemon**: A small daemon answers hotkeys instantly and collapses key-repeat bursts into one action. ⚡
-   **Config File**: Persist your preferences in `~/.config/winjitsu/config.ini`. ⚙️
-   **CLI Overrides**: Override config values when starting the daemon — no file editing needed. 🎛️


---

## 🛠️ Requirements

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


---

## 📦 Installation

### 🏹 On Arch‑based systems

WinJitsu is available in the AUR. You can install it using your favorite AUR helper (e.g., `yay`):

```bash
yay -S winjitsu
```

### 🐍 From PyPI

```bash
pip install WinJitsu
```

`xdotool` still has to come from your distribution (see Requirements above).

### Building and Installing Wheel

To install WinJitsu as a package, you can build a wheel and install it.
This uses the standard `pyproject.toml` configuration to build the package.
This allows you to run `winjitsu` from anywhere.

1.  **Install build tools**:
    ```bash
    pip install build
    ```

2.  **Build the package**:
    ```bash
    python3 -m build
    ```

3.  **Install the wheel**:
    ```bash
    pip install dist/winjitsu-*-py3-none-any.whl --force-reinstall
    ```

4.  **Run WinJitsu**:
    ```bash
    winjitsu --help
    ```

### Manual Installation (From Source)

Clone the repository and install using `pip`:

```bash
git clone https://github.com/Evilchuck666/WinJitsu.git
cd WinJitsu
pip install .
```


---

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
| `U`    | Restore the window's home position     | 🔙    |
| `TF`   | Toggle fullscreen / home position      | 🔄    |
| `TD`   | Move to the next monitor               | 📺    |
| `CC`   | Clear the window state cache           | 🧹    |

The **home position** is where a window was before WinJitsu first moved it. It is kept per window in `~/.cache/winjitsu/state.db` and reset whenever the daemon starts or you move the window yourself.


---

## ⚙️ Configuration

WinJitsu can be configured via a file or directly from the command line. CLI flags always take priority over the config file. 🏆

### Config File

The config file lives at `~/.config/winjitsu/config.ini` (respects `$XDG_CONFIG_HOME`).

```bash
winjitsu --write-config     # 📝 Save current settings to the config file
winjitsu --see-config       # 👀 Show the active config file path and values
winjitsu --read-config PATH # 📂 Use a different config file for this run
```

### Available Options

| Flag            | Config key          | Default | Description                                           |
|:----------------|:--------------------|:--------|:------------------------------------------------------|
| `--steps N`     | `[animation] steps` | `25`    | Animation steps — higher is smoother but slower 🎞️   |
| `--padding PX`  | `[display] padding` | `0`     | Gap in pixels around the window when fullscreening 📐 |
| `--delay-ms MS` | `[daemon] delay_ms` | `250`   | Delay in ms before an action fires in daemon mode ⏱️  |

### Examples

```bash
winjitsu --daemon --steps 10                    # Start daemon with snappy animation 💨
winjitsu --daemon --padding 8                   # Start daemon with a cozy fullscreen gap 🖼️
winjitsu --write-config --steps 15 --padding 4  # Save these as your defaults 💾
```


---

## ⚡ Daemon Mode

Running WinJitsu as a background daemon makes hotkey responses feel instant and prevents duplicate actions from key repeat. 🚀

```bash
winjitsu --daemon           # Start the daemon in the background
winjitsu --reload-daemon    # Restart the daemon 🔄
```

When the daemon is running, any `winjitsu [ACTION]` command is sent to it over a Unix socket. The daemon waits a short delay (configurable with `--delay-ms`) and only runs the last action of a rapid burst, so key repeat collapses into a single, clean move. ✨

> 💡 **Tip:** Start the daemon on login and bind your hotkeys to `winjitsu [ACTION]` — you'll barely notice the tool is even there.


---

## 🎹 Binding Keys

For the best experience, bind these commands to keyboard shortcuts in your window manager configuration
(e.g., i3, creating custom shortcuts in GNOME/KDE).

Example:
-   `Super + Up` -> `winjitsu N`
-   `Super + Right` -> `winjitsu E`

Happy tiling! 🎉

---

## ⚖️ License

This project is licensed under the GPLv3 License – see the [LICENSE](LICENSE) file for details.
