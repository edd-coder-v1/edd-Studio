/* Inspect the selected transcription model; downloads require an explicit click. */
(() => {
  const $=id=>document.getElementById(id);
  let revision=0, info=null, checkedModel='', downloading='', timer=null;
  const model=()=>$('whisper-model')?.value||$('ai-whisper-model')?.value||'base';
  async function request(action,name,post=false) {
    const response=await fetch(`${serverUrl}/api/setup/whisper/${action}?model=${encodeURIComponent(name)}`,{method:post?'POST':'GET',signal:AbortSignal.timeout(15000)});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||'Model request failed');
    return data;
  }
  function controls(){
    $('quality-model-download-btn').disabled=!!downloading||!info||checkedModel!==model()||info.present||!info.downloadable;
    $('quality-model-download-btn').textContent=`Download Whisper ${model()}`;
    $('quality-model-cancel').disabled=!downloading;
  }
  async function refresh(){
    const current=++revision,name=model();info=null;controls();
    $('quality-model-title').textContent=`Whisper ${name}`;
    $('quality-model-status').textContent=`Checking ${name} availability…`;
    $('quality-model-detail').textContent=`Checking Whisper ${name} on this computer…`;
    $('quality-model-refresh').disabled=true;
    try {
      const result=await request('model-status',name);
      if(current!==revision||name!==model())return;
      info=result;checkedModel=name;
      const text=result.backend==='remote'?`${name}: managed by your transcription server; no local download.`:
        !result.backend?`${name}: install a local transcription engine in Dependencies before downloading.`:
        result.present?`${name}: downloaded and ready.`:
        result.downloadable?`${name}: not downloaded. You can download it here when you choose.`:
        `${name}: download unavailable until a local transcription engine is installed. Open the Dependencies section in Settings.`;
      $('quality-model-status').textContent=text;
      $('quality-model-detail').textContent=text+(result.repo?` Model: ${result.repo}.`:'');
      $('quality-model-link').textContent=result.present?'View transcription model':'View model download options';
    }catch(error){if(current===revision){$('quality-model-status').textContent='Model availability could not be checked.';$('quality-model-detail').textContent=error.message+' — use Check availability to retry.';}}
    finally{if(current===revision){$('quality-model-refresh').disabled=false;controls();}}
  }
  function open(){
    activateView('setup');
    const panel=$('quality-model-download');
    for(let parent=panel.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
    panel.scrollIntoView({behavior:'smooth',block:'center'});panel.focus({preventScroll:true});refresh();
  }
  async function poll(name){
    try{
      const data=await request('pull-progress',name);
      if(downloading!==name)return;
      $('quality-model-progress').value=Math.max(0,Math.min(100,Number(data.percent)||0));
      $('quality-download-status').textContent=`Whisper ${name}: ${data.status||data.state} (${Math.round(data.percent||0)}%)`;
      if(data.done||['success','error','cancelled','idle'].includes(data.state)){
        downloading='';$('quality-model-progress').hidden=true;
        $('quality-download-status').textContent=data.state==='success'?`Whisper ${name} downloaded.`:data.state==='cancelled'?`Whisper ${name} download cancelled.`:data.error||`Whisper ${name}: ${data.state}. Check availability before trying again.`;
        controls();await refresh();return;
      }
      timer=setTimeout(()=>poll(name),1000);
    }catch(error){downloading='';$('quality-model-progress').hidden=true;$('quality-download-status').textContent=`Could not check the ${name} download. It may still be running. Use Download to reconnect: ${error.message}`;controls();}
  }
  $('quality-model-link').onclick=open;
  $('quality-model-refresh').onclick=refresh;
  $('quality-model-folder').onclick=()=>openModelFolder('whisper',model());
  $('quality-model-download-btn').onclick=async()=>{
    if(downloading||!info?.downloadable||info.present||checkedModel!==model())return;
    const name=model();downloading=name;controls();$('quality-model-progress').hidden=false;
    $('quality-model-progress').value=0;$('quality-download-status').textContent=`Starting the optional Whisper ${name} download…`;
    try{const data=await request('pull-start',name,true);
      if(data.already_present||data.not_needed||data.started===false&&!data.already_running){downloading='';$('quality-model-progress').hidden=true;controls();await refresh();$('quality-download-status').textContent='No download was needed or started.';return;}
      await poll(name);
    }catch(error){downloading='';$('quality-model-progress').hidden=true;$('quality-download-status').textContent=error.message;controls();}
  };
  $('quality-model-cancel').onclick=async()=>{if(!downloading)return;try{await request('pull-cancel',downloading,true);$('quality-download-status').textContent='Cancelling download…';}catch(error){$('quality-download-status').textContent=error.message;}};
  for(const id of ['whisper-model','ai-whisper-model','sidebar-whisper-model'])$(id)?.addEventListener('change',()=>queueMicrotask(refresh));
  window.addEventListener('beforeunload',()=>clearTimeout(timer));
  window.KlipzyQualityDownloads={refresh,open};
})();
