const test=require('node:test');
const assert=require('node:assert/strict');
const store=require('../ui/src/project-store.js');
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};};
test('project backup survives a corrupt primary and future versions are rejected',()=>{
  const s=storage();store.write(s,'p',[{id:'a',name:'original'}]);
  store.write(s,'p',[{id:'a',name:'changed'}]);s.setItem('p','{broken');
  assert.equal(store.read(s,'p')[0].name,'original');
  assert.throws(()=>store.migrate([{id:'future',schemaVersion:2}]));
  assert.throws(()=>store.migrate({version:2,projects:[]}));
});
test('cuts remap words once, preserve undo and use clean footage for captions',()=>{
  const clip={source_file:'original.mp4',output_file:'burned.mp4',start_time:10,end_time:15,
    words:[{word:'hello',start:10.2,end:10.8},{word:'um',start:11.2,end:11.8},{word:'world',start:13,end:13.5}]};
  store.applyCut(clip,{output_path:'cut.mp4',clean_output_path:'clean.mp4',cut_duration:4,kept_ranges:[[0,1],[2,5]]});
  assert.deepEqual(clip.words.map(w=>[w.word,w.start,w.end]),[['hello',.1999999999999993,.8000000000000007],['world',2,2.5]]);
  assert.equal(clip.source_file,'clean.mp4');assert.equal(clip.cut_history[0].start_time,10);
  assert.equal(clip.start_time,0);assert.equal(clip.srt_path,null);
});
test('invalid timing maps never mutate the original clip',()=>{
  const clip={output_file:'old.mp4'};
  assert.throws(()=>store.applyCut(clip,{kept_ranges:[[2,1]]}));
  assert.deepEqual(clip,{output_file:'old.mp4'});
});
