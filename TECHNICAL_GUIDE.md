# WinJitsu technical guide

[Back to the project overview](README.md)

WinJitsu is a Python command-line tool and background daemon that moves X11
windows with `xdotool` and detects screens with `python-xlib` (RandR).

## Configuration

WinJitsu can be configured via a file or directly from the command line. CLI flags always take priority over the config file. 🏆

### Config File

The config file lives at `~/.config/winjitsu/config.ini` (respects `$XDG_CONFIG_HOME`).

```bash
winjitsu --write-config     # 📝 Save current settings to the config file
winjitsu --see-config       # 👀 Show the active config file path and values
winjitsu --read-config PATH # 📂 Use a different config file for this run
```

### Available Options

| Flag            | Config key          | Range  | Default | Description                                                       |
|:----------------|:--------------------|:-------|:--------|:------------------------------------------------------------------|
| `--steps N`     | `[animation] steps` | 1–1000 | `25`    | Animation steps — higher is smoother but slower 🎞️             |
| `--padding PX`  | `[display] padding` | 0–500  | `0`     | Gap in pixels around the window when fullscreening 📐          |
| `--delay-ms MS` | `[daemon] delay_ms` | 0–5000 | `250`   | How long the daemon waits for a burst of key presses to end ⏱️ |

A value outside its range is rejected on the command line; in the config file it falls back to its default with a warning, without affecting the other options.

### Examples

```bash
winjitsu --daemon --steps 10                    # Start daemon with snappy animation 💨
winjitsu --daemon --padding 8                   # Start daemon with a cozy fullscreen gap 🖼️
winjitsu --write-config --steps 15 --padding 4  # Save these as your defaults 💾
```

## Daemon mode

Running WinJitsu as a background daemon makes hotkey responses feel instant and prevents duplicate actions from key repeat. 🚀

```bash
winjitsu --daemon           # Start the daemon in the background
winjitsu --reload-daemon    # Restart the daemon 🔄
```

When the daemon is running, any `winjitsu [ACTION]` command is sent to it over a Unix socket. The first action runs right away; actions that follow within a short delay (configurable with `--delay-ms`) form a burst, and only its last one runs once the burst is over — not at all if it repeats the first, so holding a key down still makes a single, clean move. ✨

The daemon writes its log to `~/.local/state/winjitsu/daemon.log` (respects `$XDG_STATE_HOME`); `winjitsu --see-config` shows the path.

> 💡 **Tip:** Start the daemon on login and bind your hotkeys to `winjitsu [ACTION]` — you'll barely notice the tool is even there.

## Installing from source

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

### Running the tests

The unit tests use the standard library only and don't need an X server:

```bash
make test   # or: PYTHONPATH=src python -m unittest discover -s tests -v
```

### Manual Installation (From Source)

Clone the repository and install using `pip`:

```bash
git clone https://github.com/Evilchuck666/WinJitsu.git
cd WinJitsu
pip install .
```
