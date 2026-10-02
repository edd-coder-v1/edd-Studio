/* Navigation-only presentation helpers. Existing controls remain the source of truth. */
(() => {
  document.querySelectorAll('[data-studio-action]').forEach(button => button.addEventListener('click', () => {
    const action = button.dataset.studioAction;
    if (action === 'new') document.getElementById('projects-new-btn')?.click();
    else document.querySelector(`.nav-item[data-view="${action}"]`)?.click();
  }));
  const settings = document.getElementById('view-setup');
  if (!settings) return;
  // Keep the existing controls/nodes while giving long settings cards a disclosure.
  for(const id of ['gpu-accel','setup-deps','ai-ollama-model','setup-recommendations','model-catalog','diarization-status']){
    const card=document.getElementById(id)?.closest('.card');
    if(!card||card.tagName==='DETAILS')continue;
    const details=document.createElement('details');details.className=card.className+' settings-disclosure';
    const heading=card.querySelector('h3'),summary=document.createElement('summary');summary.textContent=heading?.textContent||'Models';heading?.remove();details.append(summary);
    while(card.firstChild)details.append(card.firstChild);card.replaceWith(details);
  }
  const nav = document.createElement('nav');
  nav.className = 'studio-settings-nav'; nav.setAttribute('aria-label', 'Settings sections');
  const heading=document.createElement('h2');heading.textContent='Shortcuts';nav.append(heading);
  const home=document.createElement('button');home.type='button';home.className='btn btn-small btn-secondary';home.textContent='Home';
  home.addEventListener('click',()=>settings.querySelector('.view-header').scrollIntoView({block:'start',behavior:'smooth'}));nav.append(home);
  const maintenance=document.getElementById('clear-cache-btn')?.closest('.card');
  const cache=settings.querySelector('.media-cache-panel');if(maintenance&&cache)maintenance.append(cache);
  const addons=document.getElementById('diarization-status')?.closest('.card');if(maintenance&&addons)maintenance.after(addons);
  const sections = [['Hardware','setup-hardware'],['Hardware acceleration','gpu-accel'],['Local AI Model Catalog','ai-ollama-model'],['Optional AI add-ons','diarization-status'],['Dependencies','setup-deps'],['Maintenance','clear-cache-btn'],['Media cache','media-cache-status']];
  sections.forEach(([name,id]) => {
    const target = document.getElementById(id)?.closest('.card');
    if (!target) return;
    const button = document.createElement('button'); button.type='button';button.className='btn btn-small btn-secondary';button.textContent=name;
    button.addEventListener('click', () => { if(target.tagName==='DETAILS') target.open=true; target.scrollIntoView({block:'start',behavior:'smooth'}); });
    nav.append(button);
  });
  settings.querySelector('.view-header')?.after(nav);
})();
