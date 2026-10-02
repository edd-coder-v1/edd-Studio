"""Atomic local state and one shared admission slot for expensive media work."""
import functools
import json
import os
import threading
import uuid
from pathlib import Path

_HEAVY = threading.BoundedSemaphore(1)
_STATE_LOCK = threading.RLock()

def data_root():
    return Path(os.environ.get("KLIPZY_DATA_DIR") or Path(__file__).resolve().parents[2])

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

def serial_heavy(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        from server.core import proc
        while not _HEAVY.acquire(timeout=.2):
            proc.raise_if_cancelled()
        try:
            proc.raise_if_cancelled()
            return function(*args, **kwargs)
        finally:
            _HEAVY.release()
    return wrapped

def journal_job(job_id, request, result):
    # A journal failure must be visible but must not discard a successful export.
    import logging
    try:
        with _STATE_LOCK:
            atomic_json(data_root() / 'logs' / 'recovery' / (job_id + '.json'),
                        {'version': 1, 'id': job_id, 'request': request, 'result': result})
    except (OSError, ValueError):
        logging.getLogger('klipzy').exception('Could not save job recovery record')

def recovery_jobs(active_ids=()):
    records = []
    directory = data_root() / 'logs' / 'recovery'
    for path in sorted(directory.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:60]:
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if value['id'] not in active_ids and value['result'].get('status') in ('queued', 'processing'):
                value['result']['status'] = 'interrupted'
            records.append(value)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return records
