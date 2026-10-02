"""Local multicamera alignment, reviewable cut suggestions and deterministic export.

Offsets use camera_time = master_time + offset. Shared audio is aligned using
whitened energy envelopes. No cloud/model requests or source-file writes.
"""
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from server.core import proc
from server.core.ffmpeg_tools import get_media_info
from server.core.reliability import serial_heavy

def probe(path):
    info = get_media_info(path)
    video = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
    if not video:
        raise ValueError('Each camera must have a video stream')
    rate = video.get('avg_frame_rate', '30/1').split('/')
    fps = float(rate[0]) / max(1, float(rate[1])) if len(rate) == 2 else float(rate[0])
    return {'duration': float(info.get('format', {}).get('duration', 0)), 'fps': fps,
            'audio': any(s.get('codec_type') == 'audio' for s in info.get('streams', []))}

def audio_envelope(path, duration):
    import numpy as np
    result = proc.run(['ffmpeg','-v','error','-i',path,'-t',str(duration),'-vn',
                       '-ac','1','-ar','8000','-f','f32le','pipe:1'],
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(120, duration))
    if result.returncode:
        raise ValueError('Cannot read reference audio: ' + result.stderr.decode(errors='replace')[-300:])
    samples = np.frombuffer(result.stdout, dtype='<f4')
    n = len(samples)//160  # 20ms envelopes
    if n < 100:
        raise ValueError('At least two seconds of shared audio is needed')
    return np.sqrt(np.mean(samples[:n*160].reshape(n,160)**2,axis=1))

def align(reference, camera, max_offset=30):
    """Return a signed lag and peak correlation. Ambiguity must be reviewed."""
    import numpy as np
    from scipy.signal import correlate, correlation_lags
    # Limit the first alignment to ten minutes; later windows verify drift.
    n = min(len(reference),len(camera),30000)
    if n < 100:
        return {'offset':0.,'confidence':0.,'needs_review':True}
    a=np.log1p(reference[:n]*100); b=np.log1p(camera[:n]*100)
    a-=a.mean(); b-=b.mean()
    norm=float(np.linalg.norm(a)*np.linalg.norm(b))
    if norm < 1e-9:
        return {'offset':0.,'confidence':0.,'needs_review':True}
    scores=correlate(b,a,mode='full',method='fft')/norm
    lags=correlation_lags(len(b),len(a),mode='full')
    valid=np.abs(lags)<=int(max_offset*50)
    choices=np.flatnonzero(valid); best=int(choices[np.argmax(scores[valid])])
    # Score only the matched overlap: leading camera padding must not depress
    # the confidence of otherwise identical audio.
    lag=int(lags[best])
    matched_a=a[:n-lag] if lag>=0 else a[-lag:]
    matched_b=b[lag:] if lag>=0 else b[:n+lag]
    matched_a=matched_a-matched_a.mean();matched_b=matched_b-matched_b.mean()
    overlap_norm=float(np.linalg.norm(matched_a)*np.linalg.norm(matched_b))
    confidence=max(0.,min(1.,float(np.dot(matched_a,matched_b))/overlap_norm)) if overlap_norm>1e-9 else 0.
    return {'offset':round(float(lags[best])/50,3), 'confidence':round(confidence,3),
            'needs_review':confidence<.65}

def suggest_segments(cameras, start, end, reference, min_shot=5., target_shot=12., wide=0, speaker_turns=None):
    """Prefer labeled speaker turns when provided; otherwise offer pacing cuts.

    Pacing cuts are explicitly not speaker recognition. Silence selects the wide
    camera. Every decision is returned with a reason for editable review.
    """
    import numpy as np
    points=[start]; at=start
    while at+target_shot < end:
        proc.raise_if_cancelled()
        lo=at+min_shot; hi=min(end-min_shot,at+target_shot+3)
        if hi<=lo: break
        # Prefer an audio pause near the desired cut rather than cutting a word.
        a=max(0,int(max(lo,at+target_shot-3)*50)); b=min(len(reference),int(hi*50))
        candidate=(a+int(np.argmin(reference[a:b])))/50 if b>a else at+target_shot
        if candidate<=at:break
        points.append(candidate);at=candidate
    points.append(end)
    silence=float(np.percentile(reference,15))
    result=[]
    for i,(a,b) in enumerate(zip(points,points[1:])):
        available=[j for j,c in enumerate(cameras) if a+c['offset']>=-.02 and b+c['offset']<=c['duration']+.02]
        if not available:raise ValueError('There is a gap with no available camera')
        chunk=reference[int(a*50):int(b*50)]
        quiet=bool(len(chunk) and float(np.mean(chunk))<=max(1e-5,silence))
        chosen=available[i%len(available)]
        reason='Pacing suggestion near a quieter moment; review camera choice'
        if quiet and wide in available:chosen=wide;reason='Quiet section: wide camera'
        for turn in speaker_turns or []:
            if turn['start'] <= (a+b)/2 < turn['end'] and turn['camera'] in available:
                chosen=turn['camera'];reason='User-mapped speaker turn';break
        if result and result[-1]['camera']==chosen:
            result[-1]['end']=round(b,3)
        else: result.append({'start':round(a,3),'end':round(b,3),'camera':chosen,'reason':reason})
    return result

@serial_heavy
def analyze(paths, start=0., duration=120., min_shot=5., target_shot=12., wide=0, progress=None, speaker_count=0):
    progress=progress or (lambda *a:None)
    if len(paths) not in (2,3) or len(set(map(os.path.abspath, paths)))!=len(paths):
        raise ValueError('Choose two or three different camera recordings of the same event')
    cameras=[]; envelopes=[]
    for i,path in enumerate(paths):
        proc.raise_if_cancelled();progress(f'Reading camera {i+1} audio',int(i/len(paths)*60))
        item=probe(path)
        if not item['audio']:raise ValueError('Each camera needs shared audio for automatic sync. Add audio or align externally first.')
        cameras.append({'path':os.path.abspath(path),'name':Path(path).name,**item})
        envelopes.append(audio_envelope(path,item['duration']))
    warnings=[]
    for i,camera in enumerate(cameras):
        alignment={'offset':0.,'confidence':1.,'needs_review':False} if i==0 else align(envelopes[0],envelopes[i])
        camera.update(alignment)
        if i and min(len(envelopes[0]),len(envelopes[i]))>15000:
            late=align(envelopes[0][-15000:],envelopes[i][-15000:])
            # End-window positions differ when file durations differ.
            late_offset=late['offset']+(len(envelopes[i])-len(envelopes[0]))/50
            camera['drift_seconds']=round(late_offset-camera['offset'],3)
            if late['confidence']<.65 or abs(camera['drift_seconds'])>.12:
                camera['needs_review']=True
                warnings.append(f'Camera {i+1}: sync may drift; verify the beginning and end before export.')
        if alignment['needs_review']:warnings.append(f'Camera {i+1}: weak audio match. Verify or edit its offset.')
    start=max(float(start),max(-c['offset'] for c in cameras),0.)
    common_end=min(c['duration']-c['offset'] for c in cameras)
    end=min(common_end,start+float(duration))
    if end-start<2:raise ValueError('The requested range has less than two seconds of common footage')
    segments=suggest_segments(cameras,start,end,envelopes[0],min_shot,target_shot,wide)
    plan={'version':1,'master':0,'wide':wide,'start':start,'end':end,'cameras':cameras,'segments':segments,'min_shot':min_shot,'target_shot':target_shot,
            'warnings':warnings,'method':'Shared-audio synchronization with pause-aware pacing suggestions; no automatic speaker identification'}
    if speaker_count:
        from server.core.speaker_follow import detect_turns
        plan.update(detect_turns(paths[0],start,end,speaker_count,progress))
        plan['method']=plan['speaker_method']
        plan['warnings'].append('Choose a camera for each voice, then apply speaker choices. Until then, shots remain pacing suggestions.')
        plan['speaker_mapping_applied']=False
    progress('Suggestions ready for review',100)
    return plan

def validate_plan(plan):
    if plan.get('version')!=1:raise ValueError('Unsupported multicamera plan version')
    cameras=plan.get('cameras',[]);segments=plan.get('segments',[])
    if len(cameras) not in (2,3) or not segments or len(segments)>2000:raise ValueError('Invalid camera/segment count')
    start=float(plan['start']);end=float(plan['end']);cursor=start
    if not all(math.isfinite(v) for v in (start,end)) or start<0 or end<=start:raise ValueError('Invalid sequence range')
    for camera in cameras:
        if not Path(camera['path']).is_file():raise ValueError('Camera file missing: '+camera['path'])
        camera.update(probe(camera['path']))
        if not math.isfinite(float(camera['offset'])):raise ValueError('Invalid camera offset')
    for item in segments:
        a,b=float(item['start']),float(item['end']);idx=item['camera']
        if not isinstance(idx,int) or isinstance(idx,bool) or not 0<=idx<len(cameras):raise ValueError('Invalid camera index')
        camera=cameras[idx];offset=float(camera['offset'])
        if not all(math.isfinite(v) for v in (a,b)) or abs(a-cursor)>.002 or b<=a or b>end+.002:
            raise ValueError('Shots must cover the sequence in order, without gaps or overlaps')
        if a+offset<-.02 or b+offset>camera['duration']+.02:raise ValueError('A shot extends beyond its camera recording')
        cursor=b
    if abs(cursor-end)>.002:raise ValueError('Shots must cover the entire sequence')
    master=plan.get('master',0)
    if not isinstance(master,int) or not 0<=master<len(cameras):raise ValueError('Invalid main audio camera')
    if not cameras[master]['audio']:raise ValueError('Main camera has no audio stream')
    if start+cameras[master]['offset']<0 or end+cameras[master]['offset']>cameras[master]['duration']+.02:
        raise ValueError('Main audio does not cover this sequence')
    return cameras,segments

@serial_heavy
def render(plan, output, progress=None, height=1080):
    progress=progress or (lambda *a:None)
    cameras,segments=validate_plan(plan)
    target=Path(output).resolve()
    if target.exists() or target in [Path(c['path']).resolve() for c in cameras]:raise ValueError('Export must be a new file')
    target.parent.mkdir(parents=True,exist_ok=True)
    fps=cameras[0].get('fps',24000/1001)
    if not math.isfinite(fps) or fps<=0:raise ValueError('Invalid frame rate')
    first_frame=round(plan['start']*fps)
    frame_count=round(plan['end']*fps)-first_frame
    width=int(height*16/9)//2*2
    def run(args):
        proc.raise_if_cancelled()
        result=proc.run(['ffmpeg','-v','error','-y',*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if result.returncode:raise RuntimeError(result.stderr.decode(errors='replace')[-1500:])
    try:
        with tempfile.TemporaryDirectory(prefix='multicam-',dir=target.parent) as folder:
            chunks=[]
            for i,shot in enumerate(segments):
                c=cameras[shot['camera']];chunk=Path(folder)/f'{i:05d}.mp4';chunks.append(chunk)
                progress(f'Rendering shot {i+1} of {len(segments)}',int(i/len(segments)*90))
                first=round(shot['start']*fps);count=round(shot['end']*fps)-first
                if count<1:raise ValueError('Each shot must last at least one output frame')
                run(['-ss',str(max(0,first/fps+c['offset'])),'-i',c['path'],'-frames:v',str(count),
                     '-an','-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                     '-r',str(fps),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(chunk)])
            listing=Path(folder)/'shots.txt'
            listing.write_text('\n'.join("file '"+p.name+"'" for p in chunks),encoding='utf-8')
            master=cameras[plan.get('master',0)];partial=Path(folder)/'final.mp4'
            progress('Adding continuous main audio',94)
            run(['-f','concat','-safe','1','-i',str(listing),'-ss',str(first_frame/fps+master['offset']),'-i',master['path'],
                 '-map','0:v:0','-map','1:a:0','-t',str(frame_count/fps),'-c:v','copy','-c:a','aac','-b:a','192k',
                 '-movflags','+faststart',str(partial)])
            proc.raise_if_cancelled()
            # Exclusive destination: never overwrite footage or a prior export.
            os.link(partial,target)
        progress('Multicamera export complete',100)
        return str(target)
    except BaseException:
        # TemporaryDirectory owns all partial files; never remove a raced-in target.
        raise
