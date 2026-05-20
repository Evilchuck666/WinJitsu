from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("WinJitsu")
except PackageNotFoundError:
    __version__ = "unknown"

from .cli import main

__all__ = ["main"]
