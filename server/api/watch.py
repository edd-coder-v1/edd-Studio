"""API for watching an OBS / network recording folder."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.core.folder_watch import WATCHER

router = APIRouter(prefix="/watch", tags=["watch"])


class WatchConfigRequest(BaseModel):
    folder: Optional[str] = None
    enabled: Optional[bool] = None
    poll_seconds: Optional[float] = Field(default=None, ge=2, le=60)
    settle_seconds: Optional[float] = Field(default=None, ge=10, le=600)
    reset_baseline: bool = False


@router.get("/status")
def watch_status():
    return WATCHER.status()


@router.get("/recordings")
def watch_recordings():
    return {"recordings": WATCHER.list_recordings(), "status": WATCHER.status()}


@router.post("/config")
def watch_config(req: WatchConfigRequest):
    folder = req.folder
    if folder is not None and folder.strip():
        from pathlib import Path
        path = Path(folder.strip()).expanduser()
        if not path.exists():
            raise HTTPException(400, f"Folder not found: {path}. Mount the SMB share first (Finder → Connect to Server).")
        if not path.is_dir():
            raise HTTPException(400, "Path is not a folder.")
    try:
        return WATCHER.configure(
            folder=folder,
            enabled=req.enabled,
            poll_seconds=req.poll_seconds,
            settle_seconds=req.settle_seconds,
            reset_baseline=req.reset_baseline,
        )
    except OSError as exc:
        raise HTTPException(400, f"Cannot use that folder: {exc}") from exc


@router.post("/start")
def watch_start():
    status = WATCHER.status()
    if not status.get("folder"):
        raise HTTPException(400, "Choose an OBS recording folder first.")
    if not status.get("folder_ok"):
        raise HTTPException(400, "Folder is not reachable. Remount the network share and try again.")
    return WATCHER.start()


@router.post("/stop")
def watch_stop():
    return WATCHER.stop()


@router.post("/scan")
def watch_scan():
    return WATCHER.scan_now()


@router.post("/recordings/{recording_id}/dismiss")
def watch_dismiss(recording_id: str):
    try:
        return WATCHER.dismiss(recording_id)
    except KeyError:
        raise HTTPException(404, "Recording not found.") from None


@router.post("/recordings/{recording_id}/imported")
def watch_imported(recording_id: str):
    try:
        return WATCHER.mark_imported(recording_id)
    except KeyError:
        raise HTTPException(404, "Recording not found.") from None
