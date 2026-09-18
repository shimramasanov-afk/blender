from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

import numpy as np

T = TypeVar("T")


class QueueEmpty(RuntimeError):
    pass


@dataclass
class LatestOnlyQueue(Generic[T]):
    """Control path: a newer item replaces an unread one. Drops are counted."""

    _item: T | None = None
    _cond: threading.Condition = field(default_factory=threading.Condition)
    puts: int = 0
    takes: int = 0
    drops: int = 0

    def put(self, item: T) -> None:
        with self._cond:
            if self._item is not None:
                self.drops += 1
            self._item = item
            self.puts += 1
            self._cond.notify()

    def take(self) -> T:
        with self._cond:
            if self._item is None:
                raise QueueEmpty("no frame")
            item = self._item
            self._item = None
            self.takes += 1
            return item

    def take_wait(self, timeout: float) -> T:
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._item is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QueueEmpty("frame wait timed out")
                self._cond.wait(remaining)
            item = self._item
            self._item = None
            self.takes += 1
            return item

    def peek(self) -> T | None:
        with self._cond:
            return self._item

    def clear(self) -> None:
        with self._cond:
            self._item = None

    @property
    def stats(self) -> dict[str, int]:
        with self._cond:
            return {"puts": self.puts, "takes": self.takes, "drops": self.drops}


class AsyncWriter:
    """Bounded disk writer. The main loop never waits on flush."""

    def __init__(self, path: Path, *, maxsize: int = 128) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.path = path
        self.maxsize = maxsize
        self.dropped = 0
        self.enqueued = 0
        self.written = 0
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._fh = path.open("w", encoding="utf-8")
        self._thread = threading.Thread(target=self._run, name="l2-async-writer", daemon=True)
        self._thread.start()

    def put(self, row: dict[str, Any]) -> None:
        if self._stop.is_set():
            raise RuntimeError("AsyncWriter is closed")
        while True:
            try:
                self._q.put_nowait(row)
                self.enqueued += 1
                return
            except queue.Full:
                try:
                    dumped = self._q.get_nowait()
                    if dumped is not None:
                        self.dropped += 1
                except queue.Empty:
                    continue

    def _run(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=0.05)
            except queue.Empty:
                if self._stop.is_set() and self._q.empty():
                    break
                continue
            if item is None:
                break
            self._emit(item)

    def _emit(self, item: dict[str, Any]) -> None:
        kind = item.get("kind")
        if kind == "_frame":
            dest = Path(item["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            np.save(dest, item["image"])
            self.written += 1
            return
        self._fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        self._fh.flush()
        self.written += 1

    def close(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._thread.join(timeout=5.0)
        while True:
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                self._emit(item)
        self._fh.close()
