"""Watchdog-based folder watcher for new PDFs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class PDFWatcher(FileSystemEventHandler):
    """Watches for new PDF files and invokes a callback."""

    def __init__(self, callback: Callable[[Path], None]) -> None:
        self._callback = callback

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() == ".pdf":
            self._callback(path)


def watch_folder(folder: Path, callback: Callable[[Path], None], interval: float = 1.0) -> None:
    observer = Observer()
    handler = PDFWatcher(callback)
    observer.schedule(handler, str(folder), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
