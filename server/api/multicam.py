"""Background multicamera jobs using the shared media admission slot."""
import threading
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from server.core import proc, multicam
from server.core.reliability import data_root, journal_job, recovery_jobs, atomic_json

router=APIRouter(prefix='/multicam')
_JOBS={}
_LOCK=threading.RLock()

class AnalyzeRequest(BaseModel):
    paths: List[str] = Field(min_length=2,max_length=3)
    start: float = Field(default=0,ge=0,allow_inf_nan=False)
    duration: float = Field(default=120,ge=2,le=28800,allow_inf_nan=False)
    min_shot: float = Field(default=5,ge=2,le=60,allow_inf_nan=False)
    target_shot: float = Field(default=12,ge=3,le=120,allow_inf_nan=False)
    wide: int = Field(default=0,ge=0,le=2)
    speaker_count: int = Field(default=0,ge=0,le=6)

class ExportRequest(BaseModel):
    plan: dict
    output_dir: str = ''
    height: int = 1080

def start_job(kind, request, action):
    key='multicam-'+uuid.uuid4().hex[:12]
    with _LOCK:
        if sum(v['status'] in ('queued','processing') for v in _JOBS.values())>=8:
            raise HTTPException(429,'Eight multicamera jobs are already waiting or running')
        _JOBS[key]={'id':key,'status':'queued','progress':0,'step':'Waiting for media engine','error':None}
    journal_job(key,{'kind':kind,**request},dict(_JOBS[key]))
    def worker():
        proc.begin_job(key)
        def progress(step,pct):
            with _LOCK:_JOBS[key].update(status='processing',step=step,progress=pct)
        try:
            result=action(progress)
            with _LOCK:_JOBS[key].update(status='completed',progress=100,result=result)
        except proc.CancelledError:
            with _LOCK:_JOBS[key].update(status='cancelled',error='Cancelled. Original recordings were preserved.')
        except Exception as exc:
            with _LOCK:_JOBS[key].update(status='failed',error=str(exc))
        finally:
            proc.end_job()
            journal_job(key,{'kind':kind,**request},dict(_JOBS[key]))
            with _LOCK:
                completed=[k for k,v in _JOBS.items() if v['status'] in ('completed','failed','cancelled')]
                for old in completed[:-60]:_JOBS.pop(old,None)
    threading.Thread(target=worker,daemon=True).start()
    return {'job_id':key}

@router.post('/analyze')
def analyze(req:AnalyzeRequest):
    if req.speaker_count and req.duration>1800:raise HTTPException(400,'Speaker tests are limited to 30 minutes at a time')
    if req.wide>=len(req.paths) or req.target_shot<req.min_shot:raise HTTPException(400,'Check the wide camera and shot lengths')
    return start_job('multicam-analysis',req.model_dump(),lambda progress:multicam.analyze(**req.model_dump(),progress=progress))

class SequenceRequest(BaseModel):
    plan: dict
    mapping: dict
    min_shot: float = Field(default=3,ge=1,le=60,allow_inf_nan=False)

@router.post('/sequence')
def sequence(req:SequenceRequest):
    from server.core.speaker_follow import sequence as build
    try:
        plan=req.plan
        multicam.validate_plan(plan)
        plan['segments']=build(plan,req.mapping,req.min_shot)
        multicam.validate_plan(plan)
        for speaker in plan['speakers']:speaker['camera']=req.mapping.get(speaker['id'])
        plan['speaker_mapping_applied']=True
        plan['min_shot']=req.min_shot
        plan['warnings']=[w for w in plan.get('warnings',[]) if not w.startswith('Choose a camera for each voice')]
        return plan
    except (ValueError,KeyError,TypeError,OSError) as exc:raise HTTPException(400,str(exc)) from exc

@router.post('/export')
def export(req:ExportRequest):
    if req.height not in (720,1080):raise HTTPException(400,'Choose 720p or 1080p')
    if req.plan.get('speakers') and not req.plan.get('speaker_mapping_applied'):
        raise HTTPException(400,'Apply speaker choices before exporting speaker analysis')
    try:multicam.validate_plan(req.plan)
    except (ValueError,KeyError,TypeError,OSError) as exc:raise HTTPException(400,str(exc)) from exc
    directory=Path(req.output_dir).expanduser() if req.output_dir else data_root()/'output'/'multicam'
    output=directory/f'multicam-{uuid.uuid4().hex[:12]}.mp4'
    def render(progress):
        result=multicam.render(req.plan,str(output),progress,req.height)
        atomic_json(output.with_suffix('.klipzy-multicam.json'),req.plan)
        return {'output_path':result,'plan_path':str(output.with_suffix('.klipzy-multicam.json'))}
    return start_job('multicam-export',req.model_dump(),render)

@router.get('/jobs/{key}')
def status(key:str):
    with _LOCK:
        if key in _JOBS:return dict(_JOBS[key])
    for record in recovery_jobs():
        if record['id']==key:return record['result']
    raise HTTPException(404,'Job not found')

@router.post('/jobs/{key}/cancel')
def cancel(key:str):
    with _LOCK:
        if key not in _JOBS:raise HTTPException(404,'Job is not active in this session')
        if _JOBS[key]['status'] in ('queued','processing'):proc.request_cancel(key)
    return {'ok':True}
