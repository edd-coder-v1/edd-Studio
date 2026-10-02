/* Versioned local manifests with a last-good backup. No media is embedded. */
(function(root) {
  'use strict';
  function migrate(value) {
    const projects = Array.isArray(value) ? value : value?.projects;
    if (!Array.isArray(projects) || (!Array.isArray(value) && value.version !== 1)) throw new Error('Unsupported project file');
    return projects.map(p => {
      if (!p || typeof p !== 'object' || typeof p.id !== 'string') throw new Error('Invalid project record');
      if (p.schemaVersion != null && p.schemaVersion !== 1) throw new Error('Unsupported project version');
      return {...p, schemaVersion:1, clips:Array.isArray(p.clips)?p.clips:[], sources:Array.isArray(p.sources)?p.sources:[]};
    });
  }
  function read(storage,key) {
    const raw=storage.getItem(key);
    if(!raw) return [];
    try { return migrate(JSON.parse(raw)); }
    catch(error) {
      const backup=storage.getItem(key+'.backup');
      if(backup) return migrate(JSON.parse(backup));
      throw new Error('Saved projects could not be read. Import a backup before saving over them.');
    }
  }
  function write(storage,key,projects) {
    const clean=migrate(projects), previous=storage.getItem(key);
    if(previous) {
      // Never replace the last good backup with a corrupt primary record.
      try { migrate(JSON.parse(previous)); storage.setItem(key+'.backup',previous); } catch(error) {
        if(error.name==='QuotaExceededError') throw new Error('Project storage is full. Export a backup before freeing space.');
      }
    }
    storage.setItem(key,JSON.stringify(clean));
    return clean;
  }
  function remapWords(words,ranges,offset=0) {
    const out=[]; let elapsed=0;
    for(const [a,b] of ranges) {
      for(const word of words || []) {
        const start=Number(word.start)-offset,end=Number(word.end)-offset;
        const s=Math.max(a,start),e=Math.min(b,end);
        if(e>s && e-s > (end-start)*.5) out.push({...word,start:elapsed+s-a,end:elapsed+e-a});
      }
      elapsed+=b-a;
    }
    return out;
  }
  function applyCut(clip,result) {
    if(!result.kept_ranges?.length) throw new Error('The cut did not return a timing map. Original clip retained.');
    let last=0;
    for(const range of result.kept_ranges) {
      if(!Array.isArray(range)||range.length!==2||!range.every(Number.isFinite)||range[0]<last||range[1]<=range[0]) throw new Error('Invalid cut timing map. Original clip retained.');
      last=range[1];
    }
    if(!Number.isFinite(result.cut_duration)||result.cut_duration<=0||!result.output_path) throw new Error('Invalid cut output');
    const history=clip.cut_history || [];
    const before={...clip}; delete before.cut_history;
    const words=remapWords(clip.words,result.kept_ranges,Number(clip.start_time)||0);
    Object.assign(clip,{cut_history:[...history,before],original_source:clip.original_source||clip.source_file,
      source_file:result.clean_output_path||result.output_path,output_file:result.output_path,start_time:0,end_time:result.cut_duration,
      duration:result.cut_duration,words,full_text:words.map(w=>w.word).join(' '),
      srt_path:null,vtt_path:null,ass_path:null,kept_ranges:result.kept_ranges});
    return clip;
  }
  const api={migrate,read,write,remapWords,applyCut};
  if(typeof module!=='undefined') module.exports=api;
  root.KlipzyProjects=api;
})(typeof window!=='undefined'?window:globalThis);
