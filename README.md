# 🥋 WinJitsu

**WinJitsu** is a slick, animated window management tool for Linux (X11).
It allows you to effortlessly snap your active windows to various positions
on your screen with smooth animations, making your workflow feel more organic and responsive. ✨


---

## 🚀 Features

-   **Smooth Animations**: Windows glide to their new positions instead of just jumping there. 🌬️
-   **Grid Snapping**: Easily position windows to the North, South, East, West, corners, or center. 🧭
-   **Multi-Monitor Support**: Move windows between displays with ease. 🖥️ ➡️ 🖥️
-   **Fullscreen Toggling**: Smart fullscreen and restore capabilities. ↔️


---

## 🛠️ Requirements

Make sure you have the following installed on your system:

-   Python 3.6+ 🐍
-   `xdotool` (for window manipulation)
-   `xrandr` (for screen detection)

### Installing Dependencies

### 🐧 Arch‑based distributions (Arch Linux, EndeavourOS, Manjaro, etc.)

```bash
sudo pacman -S python xdotool xorg-xrandr
```

### 🐧 Debian‑based distributions (Debian, Ubuntu, Linux Mint, etc.)

```bash
sudo apt install python3 xdotool xrandr
```

### 🐧 Fedora‑based distributions (Fedora, Nobara, etc.)

```bash
sudo dnf install python3 xdotool xrandr
```


---

## 📦 Installation

### 🏹 On Arch‑based systems

WinJitsu is available in the AUR. You can install it using your favorite AUR helper (e.g., `yay`):

```bash
yay -S winjitsu
```

### Building and Installing Wheel (Recommended)

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
    pip install dist/winjitsu-0.1.0-py3-none-any.whl --force-reinstall
    ```

4.  **Run WinJitsu**:
    ```bash
    winjitsu --help
    ```

### Manual Installation (From Source)

Clone the repository and install using `pip`:

```bash
git clone https://github.com/Evilchuck666/winjitsu.git
cd winjitsu
pip install .
```


---

## 🎮 Usage

Run the command with an action argument to control the active window:

```bash
winjitsu [ACTION]
```

### Available Actions

| Action | Description | Emoji |
| :--- | :--- | :--- |
| `N` | Move to North (Top Half) | ⬆️ |
| `S` | Move to South (Bottom Half) | ⬇️ |
| `E` | Move to East (Right Half) | ➡️ |
| `W` | Move to West (Left Half) | ⬅️ |
| `NE` | Move to North-East | ↗️ |
| `NW` | Move to North-West | ↖️ |
| `SE` | Move to South-East | ↘️ |
| `SW` | Move to South-West | ↙️ |
| `C` | Center the window | 🎯 |
| `F` | Maximize / Fullscreen | 🖥️ |
| `U` | Unscreen (Restore original size/pos) | 🔙 |
| `TF` | Toggle Fullscreen | 🔄 |
| `TD` | Toggle Display (Move to other monitor) | 📺 |
| `CC` | Clear Cache | 🧹 |


---

## 🎹 Binding Keys

For the best experience, bind these commands to keyboard shortcuts in your window manager configurations
(e.g., i3, creating custom shortcuts in GNOME/KDE).

Example:
-   `Super + Up` -> `winjitsu N`
-   `Super + Right` -> `winjitsu E`

Happy tiling!

---

## ⚖️ License

This project is licensed under the GPLv3 License – see the [LICENSE](LICENSE) file for details.
