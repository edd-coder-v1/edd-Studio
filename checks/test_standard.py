"""Focused, redistributable regressions for Standard reliability and multicamera."""
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import numpy as np
import pytest
from server.core import multicam, proc, reliability

def test_alignment_recovers_signed_offset():
    rng=np.random.default_rng(7)
    audio=rng.random(10000)
    later=np.concatenate([np.zeros(75),audio])
    assert multicam.align(audio,later)['offset']==1.5
    assert multicam.align(later,audio)['offset']==-1.5
    assert multicam.align(audio,later)['confidence']>.95
    assert multicam.align(np.zeros(200),np.zeros(200))['needs_review']

def test_suggestions_cover_range_without_short_cuts():
    cameras=[{'duration':120,'offset':0}]*2
    shots=multicam.suggest_segments(cameras,0,60,np.ones(6000),5,12)
    assert shots[0]['start']==0 and shots[-1]['end']==60
    assert all(s['end']-s['start']>=5 for s in shots)
    assert all(a['end']==b['start'] for a,b in zip(shots,shots[1:]))

def test_invalid_plan_is_rejected_before_export(tmp_path,monkeypatch):
    source=tmp_path/'camera.mp4';source.touch()
    monkeypatch.setattr(multicam,'probe',lambda p:{'duration':100,'fps':24,'audio':True})
    plan={'version':1,'start':0,'end':10,'cameras':[{'path':str(source),'offset':0} for _ in range(2)],
          'segments':[{'start':0,'end':5,'camera':0},{'start':6,'end':10,'camera':1}]}
    with pytest.raises(ValueError,match='gaps'):multicam.validate_plan(plan)
    plan['segments'][1]['start']=5
    multicam.validate_plan(plan)
    plan['cameras'][1]['offset']=float('nan')
    with pytest.raises(ValueError,match='offset'):multicam.validate_plan(plan)

def test_atomic_state_keeps_previous_on_invalid_json(tmp_path):
    dest=tmp_path/'state.json'
    reliability.atomic_json(dest,{'valid':1})
    with pytest.raises(ValueError):reliability.atomic_json(dest,{'bad':float('nan')})
    assert json.loads(dest.read_text())=={'valid':1}
    assert list(tmp_path.glob('*.tmp'))==[]

def test_recovery_marks_only_abandoned_jobs(tmp_path,monkeypatch):
    monkeypatch.setenv('KLIPZY_DATA_DIR',str(tmp_path))
    reliability.journal_job('stopped',{}, {'status':'processing'})
    reliability.journal_job('live',{}, {'status':'queued'})
    values={v['id']:v['result']['status'] for v in reliability.recovery_jobs(['live'])}
    assert values=={'live':'queued','stopped':'interrupted'}

def test_heavy_work_serializes_and_cancellation_releases_slot():
    lock=threading.Lock();active=0;maximum=0
    @reliability.serial_heavy
    def work():
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active)
        time.sleep(.01)
        with lock:active-=1
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda _:work(),range(6)))
    assert maximum==1
    proc.begin_job('cancel-check');proc.request_cancel('cancel-check')
    try:
        with pytest.raises(proc.CancelledError):work()
    finally:proc.end_job()
    work()

def test_local_detector_does_not_import_ultralytics(monkeypatch):
    import sys
    from server.core.face_tracker import FaceTracker
    from server.core.local_vision import LocalFaceDetector
    monkeypatch.delenv('KLIPZY_VISION_BACKEND',raising=False)
    monkeypatch.setitem(sys.modules,'ultralytics',None)
    tracker=FaceTracker();tracker._init_model()
    assert isinstance(tracker.model,LocalFaceDetector)
    assert not tracker.model(np.zeros((240,320,3),dtype=np.uint8))[0].boxes
