from .cli import main

__all__ = ["main"]


def __getattr__(name):
    # __version__ is looked up on first use: importlib.metadata takes about as
    # long to import as the rest of the client, which runs on every hotkey.
    if name == "__version__":
        from importlib.metadata import version, PackageNotFoundError

        try:
            value = version("WinJitsu")
        except PackageNotFoundError:
            value = "unknown"

        globals()["__version__"] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
