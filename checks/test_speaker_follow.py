import copy
import numpy as np
import pytest
from server.core.speaker_follow import group_embeddings, sequence

def plan():
    return {'start':0,'end':20,'wide':0,'cameras':[{},{}],
            'speakers':[{'id':'speaker-1'},{'id':'speaker-2'}],
            'speaker_turns':[{'start':0,'end':6,'speaker':'speaker-1'},
                             {'start':6,'end':13,'speaker':'speaker-2'},
                             {'start':13,'end':20,'speaker':None}]}

def test_speaker_changes_drive_cuts_and_uncertainty_returns_to_wide():
    shots=sequence(plan(),{'speaker-1':0,'speaker-2':1},3)
    assert [(s['start'],s['end'],s['camera']) for s in shots]==[(0,6,0),(6,13,1),(13,20,0)]
    assert 'uncertain' in shots[-1]['reason']

def test_mapping_changes_camera_without_changing_audio_timeline():
    data=plan();before=copy.deepcopy(data)
    shots=sequence(data,{'speaker-1':1,'speaker-2':0},3)
    assert shots[0]['camera']==1 and shots[-1]['end']==20
    assert data==before

def test_unmapped_speaker_uses_wide_and_short_turns_do_not_flicker():
    data=plan();data['speaker_turns']=[{'start':0,'end':8,'speaker':'speaker-1'},
        {'start':8,'end':9,'speaker':'speaker-2'},{'start':9,'end':20,'speaker':'speaker-1'}]
    assert len(sequence(data,{'speaker-1':0,'speaker-2':1},3))==1
    assert sequence(plan(),{},3)==[{'start':0,'end':20,'camera':0,'reason':'Wide: uncertain, non-speech, or unmapped voice'}]

@pytest.mark.parametrize('mapping',[{'speaker-1':5},{'speaker-1':True},{'stranger':1}])
def test_invalid_mapping_rejected(mapping):
    with pytest.raises(ValueError):sequence(plan(),mapping)

def test_gaps_in_speaker_timeline_rejected():
    data=plan();data['speaker_turns'][1]['start']=7
    with pytest.raises(ValueError):sequence(data,{},3)

def test_voice_groups_are_named_in_first_occurrence_order():
    values=np.array([[1,.01,0],[.99,.02,0],[0,.01,1],[0,.02,.99],[1,0,0]])
    labels,score,margin=group_embeddings(values,2)
    assert labels.tolist()==[0,0,1,1,0]
    assert np.all(score>.99) and np.all(margin>.9)
