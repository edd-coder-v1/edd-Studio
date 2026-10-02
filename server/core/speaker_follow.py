"""Local voice grouping for reviewable camera suggestions, not person identity.

Resemblyzer's bundled voice encoder supplies embeddings; WebRTC VAD excludes
non-speech windows. Labels are local to one analysis, and camera mapping is manual.
"""
import math
import subprocess
import numpy as np
from server.core import proc


def group_embeddings(embeddings, count):
    from scipy.cluster.hierarchy import linkage, cut_tree
    values=np.asarray(embeddings,dtype=np.float64)
    values/=np.maximum(np.linalg.norm(values,axis=1,keepdims=True),1e-9)
    count=min(count,len(values))
    if len(values)==1:labels=np.zeros(1,dtype=int)
    else:labels=cut_tree(linkage(values,method='average',metric='cosine'),n_clusters=[count]).ravel()
    # Stable, easy-to-follow names ordered by first occurrence.
    order=list(dict.fromkeys(labels.tolist()))
    labels=np.array([order.index(v) for v in labels])
    centers=np.array([values[labels==i].mean(axis=0) for i in range(len(order))])
    centers/=np.maximum(np.linalg.norm(centers,axis=1,keepdims=True),1e-9)
    scores=values@centers.T
    own=scores[np.arange(len(values)),labels]
    others=scores.copy();others[np.arange(len(values)),labels]=-1
    margin=own-others.max(axis=1)
    return labels,own,margin


def detect_turns(path,start,end,count,progress=None):
    try:
        import webrtcvad
        from resemblyzer import VoiceEncoder
        from resemblyzer.audio import normalize_volume
    except ImportError as exc:
        raise ValueError('Speaker mode needs requirements-speakers.txt installed in the Klipzy Python environment.') from exc
    progress=progress or (lambda *args:None)
    if not 1<=count<=6 or not 2<=end-start<=1800:
        raise ValueError('Speaker tests support 1–6 voices and up to 30 minutes per analysis')
    progress('Reading main-camera audio for speaker analysis',62)
    result=proc.run(['ffmpeg','-v','error','-ss',str(start),'-i',path,'-t',str(end-start),
                     '-vn','-ac','1','-ar','16000','-f','f32le','pipe:1'],capture_output=True,timeout=max(120,end-start))
    if result.returncode:raise ValueError('Could not decode speaker-analysis audio')
    audio=np.frombuffer(result.stdout,dtype='<f4').copy()
    vad=webrtcvad.Vad(2)
    encoder=VoiceEncoder(device='cpu',verbose=False)
    cells=[];embeddings=[];indices=[]
    for index,t in enumerate(np.arange(0,end-start,1.)):
        proc.raise_if_cancelled()
        a=max(0,t-.5);b=min(end-start,t+1.5)
        samples=audio[int(a*16000):int(b*16000)]
        pcm=(np.clip(samples,-1,1)*32767).astype('<i2').tobytes()
        votes=[vad.is_speech(pcm[p:p+960],16000) for p in range(0,len(pcm)-959,960)]
        speech=sum(votes)/max(1,len(votes))
        cells.append({'start':round(start+t,3),'end':round(min(end,start+t+1),3),'speaker':None,'similarity':0.})
        if speech>=.5 and len(samples)>=16000 and np.sqrt(np.mean(samples**2))>1e-5:
            # Keep samples on their original timeline; never concatenate away
            # silence before assigning source timestamps.
            wav=normalize_volume(samples,-30,increase_only=True)
            embeddings.append(encoder.embed_utterance(wav));indices.append(index)
        if index%5==0:progress('Comparing local voices',min(94,65+int(29*t/(end-start))))
    if len(embeddings)<max(4,count*2):
        raise ValueError('Not enough clear speech to group voices. Choose a longer spoken section or fewer speakers.')
    labels,similarity,margin=group_embeddings(embeddings,count)
    speakers=[]
    for label in range(count):
        candidates=np.flatnonzero(labels==label)
        if not len(candidates):continue
        reliable=candidates[(similarity[candidates]>=.7)&(margin[candidates]>=.06)]
        pool=reliable if len(reliable) else candidates
        best=int(pool[np.argmax(margin[pool])]);cell=cells[indices[best]]
        speakers.append({'id':f'speaker-{label+1}','name':f'Speaker {label+1}','camera':None,
                         'sample_start':max(start,cell['start']-.5),'sample_end':min(end,cell['start']+1.5)})
    for i,cell_index in enumerate(indices):
        if similarity[i]>=.7 and margin[i]>=.06:
            cells[cell_index].update(speaker=f'speaker-{int(labels[i])+1}',similarity=round(float(similarity[i]),3))
    # Isolated one-second changes are not strong enough to trigger camera cuts.
    for i in range(1,len(cells)-1):
        if cells[i]['speaker'] not in (cells[i-1]['speaker'],cells[i+1]['speaker']):cells[i]['speaker']=None
    turns=[]
    for cell in cells:
        if turns and turns[-1]['speaker']==cell['speaker']:
            turns[-1]['end']=cell['end'];turns[-1]['similarity']=min(turns[-1]['similarity'],cell['similarity'])
        else:turns.append(dict(cell))
    known=sum(t['end']-t['start'] for t in turns if t['speaker'])
    return {'speakers':speakers,'speaker_turns':turns,'speaker_coverage':round(known/(end-start),3),
            'speaker_method':'Experimental local voice clustering (Resemblyzer + WebRTC VAD). Similarity is not a probability; verify voice groups and camera mappings.'}


def sequence(plan,mapping,min_shot=3.):
    """Follow reviewed voice mappings with a minimum hold; ambiguity uses wide."""
    if not 1<=min_shot<=60:raise ValueError('Minimum shot must be 1–60 seconds')
    records=plan.get('speakers',[])
    if not isinstance(records,list) or not 1<=len(records)<=6 or any(not isinstance(s,dict) or not isinstance(s.get('id'),str) for s in records):
        raise ValueError('Invalid speaker records')
    speakers={s['id'] for s in records}
    if len(speakers)!=len(records):raise ValueError('Duplicate speaker labels')
    if set(mapping)-speakers:raise ValueError('Unknown speaker mapping')
    count=len(plan['cameras']);wide=plan.get('wide',0)
    for camera in [wide,*[v for v in mapping.values() if v is not None]]:
        if isinstance(camera,bool) or not isinstance(camera,int) or not 0<=camera<count:raise ValueError('Invalid speaker camera')
    start,end=plan['start'],plan['end'];cursor=start;shots=[]
    turns=plan.get('speaker_turns',[])
    if not isinstance(turns,list) or not 1<=len(turns)<=3600:raise ValueError('Invalid speaker timeline')
    for turn in turns:
        if not isinstance(turn,dict) or turn.get('speaker') is not None and turn.get('speaker') not in speakers:
            raise ValueError('Unknown voice in speaker timeline')
        a,b=turn['start'],turn['end']
        if not all(math.isfinite(v) for v in (a,b)) or abs(a-cursor)>.002 or b<=a or b>end+.002:
            raise ValueError('Speaker turns must cover the sequence without gaps')
        cursor=b
        speaker=turn.get('speaker');camera=mapping.get(speaker)
        reason=f'Follow {speaker}' if camera is not None else 'Wide: uncertain, non-speech, or unmapped voice'
        camera=wide if camera is None else camera
        if not shots:shots.append({'start':a,'end':b,'camera':camera,'reason':reason})
        elif camera==shots[-1]['camera']:shots[-1]['end']=b
        else:
            boundary=max(a,shots[-1]['start']+min_shot)
            # Don't create a brief reaction cut at the end of a short turn.
            if b-boundary<min_shot:
                shots[-1]['end']=b
            else:
                shots[-1]['end']=boundary
                shots.append({'start':boundary,'end':b,'camera':camera,'reason':reason})
    if abs(cursor-end)>.002:raise ValueError('Incomplete speaker timeline')
    return shots
