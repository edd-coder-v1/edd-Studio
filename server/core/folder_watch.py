"""Watch a local/network folder for OBS (or similar) recordings.

Polls a directory for video files. While a file's size keeps growing it is
treated as an in-progress recording; once size+mtime stay stable for
``settle_seconds`` it becomes ready to import into Edd Studio.

Designed for SMB/NAS mounts (OBS on another PC → shared folder → Mac).
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger("klipzy.folder_watch")

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".ts"}

# Defaults tuned for network shares (OBS remux / SMB flush lag).
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_SETTLE_SECONDS = 45.0


def _state_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs / "obs_folder_watch.json"


class FolderWatcher:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.folder: str = ""
        self.enabled: bool = False
        self.poll_seconds: float = DEFAULT_POLL_SECONDS
        self.settle_seconds: float = DEFAULT_SETTLE_SECONDS
        # path → recording dict
        self._recordings: Dict[str, Dict[str, Any]] = {}
        # Paths present when watch was first enabled for this folder (no alert).
        self._baseline: set[str] = set()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        path = _state_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _LOG.warning("Could not load folder-watch state: %s", exc)
            return
        self.folder = str(data.get("folder") or "")
        self.enabled = bool(data.get("enabled"))
        self.poll_seconds = float(data.get("poll_seconds") or DEFAULT_POLL_SECONDS)
        self.settle_seconds = float(data.get("settle_seconds") or DEFAULT_SETTLE_SECONDS)
        self._baseline = set(data.get("baseline") or [])
        for item in data.get("recordings") or []:
            key = item.get("path")
            if key:
                self._recordings[key] = item

    def _save(self) -> None:
        payload = {
            "folder": self.folder,
            "enabled": self.enabled,
            "poll_seconds": self.poll_seconds,
            "settle_seconds": self.settle_seconds,
            "baseline": sorted(self._baseline),
            "recordings": list(self._recordings.values()),
        }
        path = _state_path()
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            _LOG.warning("Could not save folder-watch state: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        with self._lock:
            folder_ok = bool(self.folder and Path(self.folder).expanduser().is_dir())
            return {
                "folder": self.folder,
                "enabled": self.enabled,
                "running": bool(self._thread and self._thread.is_alive()),
                "folder_ok": folder_ok,
                "poll_seconds": self.poll_seconds,
                "settle_seconds": self.settle_seconds,
                "recording_count": sum(
                    1 for r in self._recordings.values() if r.get("status") == "recording"
                ),
                "ready_count": sum(
                    1 for r in self._recordings.values() if r.get("status") == "ready"
                ),
            }

    def configure(
        self,
        folder: Optional[str] = None,
        enabled: Optional[bool] = None,
        poll_seconds: Optional[float] = None,
        settle_seconds: Optional[float] = None,
        reset_baseline: bool = False,
    ) -> Dict[str, Any]:
        with self._lock:
            if folder is not None:
                new_folder = str(Path(folder.strip()).expanduser()) if folder.strip() else ""
                if new_folder != self.folder:
                    self.folder = new_folder
                    self._baseline.clear()
                    # Keep dismissed/imported history only for paths under the new folder.
                    if new_folder:
                        prefix = str(Path(new_folder).resolve()) if Path(new_folder).exists() else new_folder
                        self._recordings = {
                            k: v for k, v in self._recordings.items()
                            if k.startswith(prefix) or k.startswith(new_folder)
                        }
                    else:
                        self._recordings.clear()
                    reset_baseline = True
            if poll_seconds is not None:
                self.poll_seconds = max(2.0, min(60.0, float(poll_seconds)))
            if settle_seconds is not None:
                self.settle_seconds = max(10.0, min(600.0, float(settle_seconds)))
            if enabled is not None:
                self.enabled = bool(enabled)
            if reset_baseline and self.folder:
                self._baseline = self._scan_paths_unlocked()
                # Mark baseline files as known/dismissed so they don't pop as new.
                now = time.time()
                for p in self._baseline:
                    if p not in self._recordings:
                        self._recordings[p] = self._make_recording(p, status="known", now=now)
            self._save()
            if self.enabled and self.folder:
                self._ensure_thread_unlocked()
            elif not self.enabled:
                self._stop.set()
            return self.status()

    def list_recordings(self) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._recordings.values())
        # Newest activity first; hide pure baseline "known" unless still on disk recently.
        visible = [r for r in items if r.get("status") in ("recording", "ready", "imported", "dismissed")]
        visible.sort(key=lambda r: float(r.get("updated_at") or 0), reverse=True)
        return visible

    def dismiss(self, recording_id: str) -> Dict[str, Any]:
        with self._lock:
            rec = self._find_by_id(recording_id)
            if not rec:
                raise KeyError(recording_id)
            rec["status"] = "dismissed"
            rec["updated_at"] = time.time()
            self._save()
            return dict(rec)

    def mark_imported(self, recording_id: str) -> Dict[str, Any]:
        with self._lock:
            rec = self._find_by_id(recording_id)
            if not rec:
                raise KeyError(recording_id)
            rec["status"] = "imported"
            rec["updated_at"] = time.time()
            self._save()
            return dict(rec)

    def scan_now(self) -> Dict[str, Any]:
        with self._lock:
            self._tick_unlocked()
            self._save()
            return self.status()

    def start(self) -> Dict[str, Any]:
        return self.configure(enabled=True)

    def stop(self) -> Dict[str, Any]:
        return self.configure(enabled=False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _find_by_id(self, recording_id: str) -> Optional[Dict[str, Any]]:
        for rec in self._recordings.values():
            if rec.get("id") == recording_id:
                return rec
        return None

    def _make_recording(self, path: str, status: str, now: float, size: int = 0, mtime: float = 0.0) -> Dict[str, Any]:
        name = Path(path).name
        return {
            "id": uuid.uuid4().hex[:12],
            "path": path,
            "name": name,
            "status": status,
            "size": int(size),
            "mtime": float(mtime),
            "stable_since": now if status in ("ready", "known") else None,
            "detected_at": now,
            "updated_at": now,
            "bytes_per_sec": 0.0,
        }

    def _scan_paths_unlocked(self) -> set[str]:
        folder = Path(self.folder).expanduser() if self.folder else None
        if not folder or not folder.is_dir():
            return set()
        found: set[str] = set()
        try:
            for entry in folder.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in VIDEO_EXTS:
                    continue
                # Skip OBS temporary fragments if present.
                name = entry.name.lower()
                if name.endswith(".tmp") or name.endswith(".part"):
                    continue
                try:
                    found.add(str(entry.resolve()))
                except OSError:
                    found.add(str(entry))
        except OSError as exc:
            _LOG.warning("Folder watch scan failed for %s: %s", folder, exc)
        return found

    def _stat(self, path: str) -> Optional[tuple[int, float]]:
        try:
            st = Path(path).stat()
            return int(st.st_size), float(st.st_mtime)
        except OSError:
            return None

    def _tick_unlocked(self) -> None:
        if not self.folder:
            return
        paths = self._scan_paths_unlocked()
        now = time.time()

        # New files
        for path in paths:
            if path in self._recordings:
                continue
            if path in self._baseline:
                # First-seen after baseline rebuild already handled; treat as known.
                self._recordings[path] = self._make_recording(path, status="known", now=now)
                continue
            info = self._stat(path)
            size, mtime = info if info else (0, 0.0)
            rec = self._make_recording(path, status="recording", now=now, size=size, mtime=mtime)
            self._recordings[path] = rec
            _LOG.info("Detected new recording: %s (%s bytes)", path, size)

        # Update existing
        for path, rec in list(self._recordings.items()):
            if rec.get("status") in ("dismissed", "imported", "known"):
                # Still refresh size for known→ready if user wants? Skip.
                if path not in paths and rec.get("status") == "recording":
                    # File vanished mid-record — drop.
                    del self._recordings[path]
                continue
            if path not in paths:
                if rec.get("status") == "recording":
                    del self._recordings[path]
                continue
            info = self._stat(path)
            if not info:
                continue
            size, mtime = info
            prev_size = int(rec.get("size") or 0)
            prev_mtime = float(rec.get("mtime") or 0)
            grew = size > prev_size or abs(mtime - prev_mtime) > 0.5
            elapsed = max(0.001, now - float(rec.get("updated_at") or now))
            if size > prev_size:
                rec["bytes_per_sec"] = (size - prev_size) / elapsed
            rec["size"] = size
            rec["mtime"] = mtime
            rec["updated_at"] = now

            if grew:
                rec["status"] = "recording"
                rec["stable_since"] = None
            else:
                if rec.get("stable_since") is None:
                    rec["stable_since"] = now
                stable_for = now - float(rec["stable_since"])
                if stable_for >= self.settle_seconds and rec.get("status") != "ready":
                    rec["status"] = "ready"
                    _LOG.info("Recording ready: %s (%.0f s stable, %s bytes)", path, stable_for, size)

        # Prune very old dismissed/imported (keep last 40)
        terminal = [r for r in self._recordings.values() if r.get("status") in ("dismissed", "imported", "known")]
        if len(terminal) > 40:
            terminal.sort(key=lambda r: float(r.get("updated_at") or 0))
            for old in terminal[:-40]:
                self._recordings.pop(old["path"], None)

    def _ensure_thread_unlocked(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop.clear()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="obs-folder-watch", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        _LOG.info("OBS folder watcher started")
        while not self._stop.is_set():
            try:
                with self._lock:
                    if not self.enabled:
                        break
                    self._tick_unlocked()
                    self._save()
                    wait = self.poll_seconds
            except Exception as exc:  # noqa: BLE001 — never kill the watcher thread
                _LOG.exception("Folder watch tick failed: %s", exc)
                wait = self.poll_seconds
            self._stop.wait(wait)
        _LOG.info("OBS folder watcher stopped")


WATCHER = FolderWatcher()
# Resume watcher after app restart if the user left it enabled.
if WATCHER.enabled and WATCHER.folder:
    try:
        with WATCHER._lock:
            WATCHER._ensure_thread_unlocked()
    except Exception as _exc:  # noqa: BLE001
        _LOG.warning("Could not resume folder watcher: %s", _exc)
