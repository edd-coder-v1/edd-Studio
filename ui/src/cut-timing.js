/* Cut metadata is saved even if sidecar regeneration fails: Undo remains available. */
async function refreshCutSubtitles(clip) {
  if (!clip.words?.length) return;
  try {
    const output = clip.output_file.replace(/\.[^.\\/]+$/, '') + '.srt';
    const options = typeof collectCaptionOptions === 'function' ? collectCaptionOptions() : {};
    const response = await fetch(serverUrl + '/export/subtitles', {
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({...options,output_path:output,words:clip.words,re_render:false}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Could not regenerate subtitles');
    clip.srt_path=result.export_path;clip.ass_path=result.ass_path;
    delete clip.subtitle_error;
  } catch(error) {
    clip.subtitle_error=error.message;
    showToast('Video cut saved. Subtitle regeneration failed; reopen the caption editor to retry.','error');
  }
}
