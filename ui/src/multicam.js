/* Local, reviewable multicamera workspace. Originals are never modified. */
(() => {
  // Kept for separate development; excluded from the current public UI.
  const MULTICAMERA_ENABLED = false;
  if (!MULTICAMERA_ENABLED) return;
  const $=id=>document.getElementById(id); let cameras=[],plan=null,job=null,timer=null,folder='';
  const status=text=>{$('mc-status').textContent=text;};
  const nav=document.createElement('button');nav.className='nav-item';nav.dataset.view='multicam';nav.innerHTML='<svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="2" y="3" width="13" height="10" rx="2"/><path d="m15 6 6-3v10l-6-3M5 16v4h13v-4M9 16v4"/></svg><span>Multicamera</span>';
  nav.addEventListener('click',()=>activateView('multicam'));document.querySelector('.nav').append(nav);
  async function api(path,body) {
    const res=await fetch(serverUrl+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await res.json();if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));return data;
  }
  function persist(){try{localStorage.setItem('klipzy.multicam.v1',JSON.stringify({cameras,plan,job,folder}));}catch(e){status('Draft could not be saved. Use Save sequence file.');}}
  function dirty(){ $('mc-reviewed').checked=false;persist(); }
  function restoreSettings(){if(!plan)return;$('mc-mode').value=plan.speakers?.length?'speakers':'pacing';$('mc-speaker-count').value=plan.speakers?.length||3;$('mc-start').value=plan.start;$('mc-duration').value=plan.end-plan.start;$('mc-wide').value=plan.wide||0;$('mc-min').value=plan.min_shot||3;$('mc-target').value=plan.target_shot||12;}
  function number(value,change,step='.001') {const input=document.createElement('input');input.type='number';input.step=step;input.value=value;input.style.width='100px';input.addEventListener('change',()=>{const next=Number(input.value);if(!input.value||!Number.isFinite(next)){input.value=value;return;}change(next);dirty();renderShots();});return input;}
  function renderCameras(){
    $('mc-cameras').replaceChildren();
    cameras.forEach((c,i)=>{const row=document.createElement('p');row.append(document.createTextNode(`Camera ${i+1}: ${c.name || c.path.split(/[\\/]/).pop()} `));
      if(plan){row.append(document.createTextNode('Offset (s) '),number(c.offset,v=>{c.offset=v;}));row.append(document.createTextNode(` Match: ${Math.round(c.confidence*100)}%${c.needs_review?' — verify sync':''}`));}
      const replace=document.createElement('button');replace.className='btn btn-small';replace.textContent='Relink';replace.onclick=async()=>{const path=await window.clipperAPI.selectCameraClip();if(path){c.path=path;c.name=path.split(/[\\/]/).pop();dirty();renderCameras();}};row.append(replace);$('mc-cameras').append(row);
    });
  }
  function preview(shot){const c=cameras[shot.camera],vid=$('mc-preview');vid.onloadedmetadata=()=>{vid.currentTime=shot.start+c.offset;vid.play().catch(()=>{});};vid.src=fileUrl(c.path);vid.ontimeupdate=()=>{if(vid.currentTime>=shot.end+c.offset)vid.pause();};}
  function renderShots(){
    renderSpeakers();
    $('mc-shots').replaceChildren();if(!plan)return;
    plan.segments.forEach((shot,i)=>{
      const tr=document.createElement('tr');const cell=value=>{const td=document.createElement('td');td.append(value);tr.append(td);return td;};
      cell(number(shot.start,v=>{shot.start=v;if(i)plan.segments[i-1].end=v;else plan.start=v;}));
      cell(number(shot.end,v=>{shot.end=v;if(i+1<plan.segments.length)plan.segments[i+1].start=v;else plan.end=v;}));
      const select=document.createElement('select');cameras.forEach((c,j)=>{const o=document.createElement('option');o.value=j;o.textContent='Camera '+(j+1);select.append(o);});select.value=shot.camera;
      select.onchange=()=>{shot.camera=Number(select.value);shot.reason='Your camera choice';dirty();renderShots();};cell(select);cell(document.createTextNode(shot.reason||'Your shot'));
      const actions=cell(document.createElement('span'));
      for(const [label,fn] of [['Preview',()=>preview(shot)],['Split',()=>{const mid=(shot.start+shot.end)/2;plan.segments.splice(i,1,{...shot,end:mid},{...shot,start:mid});dirty();renderShots();}],['Merge next',()=>{if(i+1<plan.segments.length){shot.end=plan.segments[i+1].end;plan.segments.splice(i+1,1);dirty();renderShots();}}]]){const b=document.createElement('button');b.className='btn btn-small';b.textContent=label;b.onclick=fn;actions.append(b);}
      $('mc-shots').append(tr);
    });
  }
  function renderSpeakers(){
    const panel=$('mc-speaker-panel');panel.hidden=!plan?.speakers?.length;
    if(panel.hidden)return;
    $('mc-speaker-summary').textContent=`${Math.round((plan.speaker_coverage||0)*100)}% of the analyzed time has a suggested voice label (not an accuracy score). Preview each voice, choose its camera, correct turns if needed, then apply. Uncertain or unmapped voices use the wide camera.`;
    $('mc-speaker-mapping').replaceChildren();
    plan.speakers.forEach(s=>{
      const row=document.createElement('p');row.append(document.createTextNode(s.name+' '));
      const listen=document.createElement('button');listen.className='btn btn-small';listen.textContent='Preview voice';listen.onclick=()=>preview({camera:plan.master||0,start:s.sample_start,end:s.sample_end});row.append(listen);
      const select=document.createElement('select');select.setAttribute('aria-label',s.name+' camera');
      const unknown=document.createElement('option');unknown.value='';unknown.textContent='Unmapped — wide camera';select.append(unknown);
      cameras.forEach((c,i)=>{const option=document.createElement('option');option.value=i;option.textContent='Camera '+(i+1);select.append(option);});select.value=s.camera??'';
      select.onchange=()=>{s.camera=select.value===''?null:Number(select.value);plan.speaker_mapping_applied=false;dirty();};row.append(select);$('mc-speaker-mapping').append(row);
    });
    $('mc-turns').replaceChildren();
    (plan.speaker_turns||[]).forEach(turn=>{
      const row=document.createElement('p');row.append(document.createTextNode(`${turn.start.toFixed(1)}–${turn.end.toFixed(1)}s `));
      const listen=document.createElement('button');listen.className='btn btn-small';listen.textContent='Preview turn';listen.onclick=()=>preview({camera:plan.master||0,start:turn.start,end:turn.end});row.append(listen);
      const select=document.createElement('select');select.setAttribute('aria-label','Voice at '+turn.start+' seconds');
      [{id:'',name:'Uncertain / non-speech'},...plan.speakers].forEach(s=>{const o=document.createElement('option');o.value=s.id;o.textContent=s.name;select.append(o);});select.value=turn.speaker||'';
      select.onchange=()=>{turn.speaker=select.value||null;turn.corrected=true;plan.speaker_mapping_applied=false;dirty();};row.append(select);$('mc-turns').append(row);
    });
  }
  $('mc-apply-speakers').onclick=async()=>{
    if(!plan?.speakers)return;
    try{busy(true);plan=await api('/multicam/sequence',{plan,mapping:Object.fromEntries(plan.speakers.map(s=>[s.id,s.camera??null])),min_shot:Number($('mc-min').value)});cameras=plan.cameras;renderShots();dirty();status('Speaker choices applied. Review the suggested cuts before export.');}
    catch(e){status(e.message);}finally{busy(false);}
  };
  function busy(value){['mc-pick','mc-analyze','mc-export','mc-load','mc-apply-speakers'].forEach(id=>$(id).disabled=value);$('mc-cancel').disabled=!value;}
  async function poll(){
    if(!job)return;
    try{
      const data=await api('/multicam/jobs/'+job);status(`${data.step||data.status} · ${data.progress||0}%`);
      if(['completed','failed','cancelled','interrupted'].includes(data.status)){
        job=null;busy(false);
        if(data.status==='completed'){
          if(data.result?.cameras){plan=data.result;cameras=plan.cameras;restoreSettings();renderCameras();renderShots();dirty();status(plan.method+'. '+plan.warnings.join(' '));}
          else if(data.result?.output_path){status('Export complete: '+data.result.output_path);showAlert('Multicamera export complete.','Export complete',data.result.output_path);}
        } else status(data.error||'The previous job was interrupted. Your sequence can be reviewed and exported again.');
        persist();return;
      }
    }catch(e){status('Could not read job status: '+e.message+' — retrying.');}
    timer=setTimeout(poll,1500);
  }
  async function start(path,body){try{busy(true);const data=await api(path,body);job=data.job_id;persist();poll();}catch(e){busy(false);status(e.message);}}
  $('mc-pick').onclick=async()=>{const paths=await window.clipperAPI.selectVideosMulti();if(!paths.length)return;if(paths.length<2||paths.length>3){status('Choose two or three camera recordings.');return;}cameras=paths.map(path=>({path}));plan=null;dirty();renderCameras();renderShots();};
  $('mc-analyze').onclick=()=>start('/multicam/analyze',{paths:cameras.map(c=>c.path),start:Number($('mc-start').value),duration:Number($('mc-duration').value),min_shot:Number($('mc-min').value),target_shot:Number($('mc-target').value),wide:Number($('mc-wide').value),speaker_count:$('mc-mode').value==='speakers'?Number($('mc-speaker-count').value):0});
  $('mc-cancel').onclick=async()=>{if(job)try{await api('/multicam/jobs/'+job+'/cancel',{});status('Cancelling…');}catch(e){status(e.message);}};
  $('mc-wide').onchange=()=>{if(plan){const next=Number($('mc-wide').value);if(next>=cameras.length){$('mc-wide').value=plan.wide;status('That camera is not in this sequence.');return;}plan.wide=next;plan.speaker_mapping_applied=false;dirty();}};
  $('mc-save').onclick=()=>{if(!plan){status('Create a sequence first.');return;}const url=URL.createObjectURL(new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='sequence.klipzy-multicam.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  $('mc-load').onclick=()=>$('mc-plan-file').click();
  $('mc-plan-file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>10*1024*1024)throw new Error('Sequence file is too large');const value=JSON.parse(await file.text());if(value.version!==1||!Array.isArray(value.cameras)||!Array.isArray(value.segments)||value.cameras.length<2||value.cameras.length>3)throw new Error('Unsupported sequence file');plan=value;cameras=plan.cameras;restoreSettings();dirty();renderCameras();renderShots();status('Sequence restored. Verify footage paths and synchronization.');}catch(e){status(e.message);}finally{e.target.value='';}};
  $('mc-folder').onclick=async()=>{const selected=await window.clipperAPI.selectOutputFolder(folder);if(selected){folder=selected;$('mc-output-folder').textContent=folder;persist();}};
  $('mc-export').onclick=()=>{if(plan?.speakers?.length&&!plan.speaker_mapping_applied){status('Apply speaker choices before exporting this speaker analysis.');return;}if(!plan||!$('mc-reviewed').checked){status('Review synchronization and check the confirmation before exporting.');return;}start('/multicam/export',{plan,output_dir:folder,height:Number($('mc-height').value)});};
  try{const saved=JSON.parse(localStorage.getItem('klipzy.multicam.v1'));if(saved){({cameras,plan,job,folder}=saved);if(plan)cameras=plan.cameras;restoreSettings();renderCameras();renderShots();$('mc-output-folder').textContent=folder||'';if(job){busy(true);timer=setTimeout(poll,1500);}}}catch(e){status('Could not restore the last sequence. Open a saved sequence file.');}
  window.addEventListener('beforeunload',()=>clearTimeout(timer));
})();
