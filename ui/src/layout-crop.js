/*
 * Same-source layout crop editor — one uploaded video, two draggable boxes
 * (gameplay + facecam), like the clip editor overlays.
 *
 * Exposes window.EddLayoutCrop:
 *   refresh({ sourcePath, fileUrl })
 *   getCrops() -> { game_crop, cam_crop }
 *   bind()
 */
(function (root) {
  'use strict';

  // Defaults: gameplay = most of the frame; facecam = typical corner webcam inset
  var gameCrop = { x: 0, y: 0, w: 1, h: 0.72 };
  var camCrop = { x: 0.72, y: 0.02, w: 0.26, h: 0.26 };
  var bound = false;

  function $(id) { return document.getElementById(id); }

  function clampCrop(crop) {
    var w = Math.max(0.05, Math.min(1, crop.w));
    var h = Math.max(0.05, Math.min(1, crop.h));
    return {
      x: Math.max(0, Math.min(1 - w, crop.x)),
      y: Math.max(0, Math.min(1 - h, crop.y)),
      w: w,
      h: h,
    };
  }

  function displayedRect(stage, video) {
    if (!stage || !video || !video.videoWidth) return null;
    var sw = stage.clientWidth, sh = stage.clientHeight;
    var vw = video.videoWidth, vh = video.videoHeight;
    var scale = Math.min(sw / vw, sh / vh);
    var dw = vw * scale, dh = vh * scale;
    return { left: (sw - dw) / 2, top: (sh - dh) / 2, w: dw, h: dh };
  }

  function paint(overlay, crop, rect) {
    if (!overlay || !rect) return;
    overlay.style.left = (rect.left + rect.w * crop.x) + 'px';
    overlay.style.top = (rect.top + rect.h * crop.y) + 'px';
    overlay.style.width = (rect.w * crop.w) + 'px';
    overlay.style.height = (rect.h * crop.h) + 'px';
  }

  function syncHidden() {
    gameCrop = clampCrop(gameCrop);
    camCrop = clampCrop(camCrop);
    var g = $('process-game-crop');
    var c = $('process-cam-crop');
    if (g) g.value = JSON.stringify(gameCrop);
    if (c) c.value = JSON.stringify(camCrop);
  }

  function syncSliders() {
    var gw = $('layout-game-w'), gh = $('layout-game-h');
    var cw = $('layout-cam-w'), ch = $('layout-cam-h');
    if (gw) gw.value = String(Math.round(gameCrop.w * 100));
    if (gh) gh.value = String(Math.round(gameCrop.h * 100));
    if (cw) cw.value = String(Math.round(camCrop.w * 100));
    if (ch) ch.value = String(Math.round(camCrop.h * 100));
  }

  function updateOverlays() {
    var stage = $('layout-source-stage');
    var vid = $('layout-source-video');
    var rect = displayedRect(stage, vid);
    paint($('layout-game-overlay'), gameCrop, rect);
    paint($('layout-cam-overlay'), camCrop, rect);
    syncHidden();
    drawResultPreview();
  }

  function currentLayoutSettings() {
    var layout = ($('process-layout') && $('process-layout').value) || 'stacked_cam_bottom';
    var splitPct = Number(($('process-cam-split') && $('process-cam-split').value) || 30);
    var side = ($('process-stacked-side') && $('process-stacked-side').value) || 'bottom';
    if (layout.indexOf('stacked') === 0) {
      layout = side === 'top' ? 'stacked_cam_top' : 'stacked_cam_bottom';
    }
    return {
      layout: layout,
      split: Math.max(0.15, Math.min(0.5, (isFinite(splitPct) ? splitPct : 30) / 100)),
      camScale: parseFloat(($('process-cam-scale') && $('process-cam-scale').value) || '0.3') || 0.3,
      camPosition: ($('process-cam-position') && $('process-cam-position').value) || 'bottom-right',
    };
  }

  function drawCropInto(ctx, video, crop, dx, dy, dw, dh) {
    if (!video.videoWidth || video.readyState < 2) return;
    var sx = crop.x * video.videoWidth;
    var sy = crop.y * video.videoHeight;
    var sw = crop.w * video.videoWidth;
    var sh = crop.h * video.videoHeight;
    var target = dw / dh;
    if (sw / sh > target) {
      sx += (sw - sh * target) / 2;
      sw = sh * target;
    } else {
      sy += (sh - sw / target) / 2;
      sh = sw / target;
    }
    ctx.drawImage(video, sx, sy, sw, sh, dx, dy, dw, dh);
  }

  function pipOrigin(position, W, H, cw, ch, pad) {
    pad = pad || 6;
    var pos = String(position || 'bottom-right').replace(/_/g, '-');
    var cx = Math.max(pad, Math.round((W - cw) / 2));
    var cy = Math.max(pad, Math.round((H - ch) / 2));
    if (pos === 'bottom-left') return { x: pad, y: H - ch - pad };
    if (pos === 'top-right') return { x: W - cw - pad, y: pad };
    if (pos === 'top-left') return { x: pad, y: pad };
    if (pos === 'top-center' || pos === 'top-middle') return { x: cx, y: pad };
    if (pos === 'bottom-center' || pos === 'bottom-middle') return { x: cx, y: H - ch - pad };
    if (pos === 'center' || pos === 'middle') return { x: cx, y: cy };
    if (pos === 'left' || pos === 'center-left') return { x: pad, y: cy };
    if (pos === 'right' || pos === 'center-right') return { x: W - cw - pad, y: cy };
    return { x: W - cw - pad, y: H - ch - pad };
  }

  function drawResultPreview() {
    var video = $('layout-source-video');
    var canvas = $('layout-result-canvas');
    var caption = $('layout-result-caption');
    if (!canvas || !video || !video.videoWidth || video.readyState < 2) return;
    var settings = currentLayoutSettings();
    var W = 270, H = 480;
    canvas.width = W;
    canvas.height = H;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, W, H);

    var g = clampCrop(gameCrop);
    var c = clampCrop(camCrop);
    var layout = settings.layout || '';

    if (layout === 'pip' || layout === 'pip_9_16') {
      drawCropInto(ctx, video, g, 0, 0, W, H);
      var cw = Math.round(W * Math.max(0.15, Math.min(0.5, settings.camScale)));
      var ch = Math.round(cw * 9 / 16);
      if (ch > H * 0.4) {
        ch = Math.round(H * 0.4);
        cw = Math.round(ch * 16 / 9);
      }
      var origin = pipOrigin(settings.camPosition, W, H, cw, ch, 6);
      ctx.fillStyle = '#fff';
      ctx.fillRect(origin.x - 2, origin.y - 2, cw + 4, ch + 4);
      drawCropInto(ctx, video, c, origin.x, origin.y, cw, ch);
      if (caption) caption.textContent = 'PiP preview · ' + (settings.camPosition || 'bottom-right');
      return;
    }

    // stacked (default for dual layouts)
    var camH = Math.round(H * settings.split);
    var mainH = H - camH;
    var camTop = layout === 'stacked_cam_top';
    drawCropInto(ctx, video, g, 0, camTop ? camH : 0, W, mainH);
    drawCropInto(ctx, video, c, 0, camTop ? 0 : mainH, W, camH);
    if (caption) caption.textContent = camTop ? 'Stacked preview · facecam top' : 'Stacked preview · facecam bottom';
  }

  function bindDrag(overlayId, which) {
    var el = $(overlayId);
    if (!el || el.dataset.bound === '1') return;
    el.dataset.bound = '1';
    el.addEventListener('pointerdown', function (event) {
      event.preventDefault();
      event.stopPropagation();
      el.setPointerCapture(event.pointerId);
      var rect = displayedRect($('layout-source-stage'), $('layout-source-video'));
      if (!rect) return;
      var start = { x: event.clientX, y: event.clientY };
      var initial = which === 'cam' ? { ...camCrop } : { ...gameCrop };
      function move(e) {
        var nx = initial.x + (e.clientX - start.x) / rect.w;
        var ny = initial.y + (e.clientY - start.y) / rect.h;
        if (which === 'cam') {
          camCrop.x = nx; camCrop.y = ny; camCrop = clampCrop(camCrop);
        } else {
          gameCrop.x = nx; gameCrop.y = ny; gameCrop = clampCrop(gameCrop);
        }
        updateOverlays();
      }
      function up() {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.removeEventListener('pointercancel', up);
      }
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
      el.addEventListener('pointercancel', up);
    });
    el.addEventListener('keydown', function (e) {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
      e.preventDefault();
      var dx = e.key === 'ArrowLeft' ? -0.01 : e.key === 'ArrowRight' ? 0.01 : 0;
      var dy = e.key === 'ArrowUp' ? -0.01 : e.key === 'ArrowDown' ? 0.01 : 0;
      if (which === 'cam') {
        camCrop.x += dx; camCrop.y += dy; camCrop = clampCrop(camCrop);
      } else {
        gameCrop.x += dx; gameCrop.y += dy; gameCrop = clampCrop(gameCrop);
      }
      updateOverlays();
    });
  }

  function formatTime(sec) {
    if (!isFinite(sec) || sec < 0) sec = 0;
    var m = Math.floor(sec / 60);
    var s = Math.floor(sec % 60);
    return m + ':' + String(s).padStart(2, '0');
  }

  function syncTransport() {
    var video = $('layout-source-video');
    var seek = $('layout-seek');
    var label = $('layout-time-label');
    var toggle = $('layout-play-toggle');
    if (!video) return;
    var dur = isFinite(video.duration) ? video.duration : 0;
    if (seek) {
      seek.max = String(dur || 0);
      if (!seek.matches(':active')) seek.value = String(video.currentTime || 0);
    }
    if (label) label.textContent = formatTime(video.currentTime || 0) + ' / ' + formatTime(dur);
    if (toggle) toggle.textContent = video.paused ? '▶ Play' : '⏸ Pause';
  }

  function setVideoSrc(video, path, fileUrlFn) {
    if (!video) return;
    if (!path) {
      video.removeAttribute('src');
      video.load();
      syncTransport();
      return;
    }
    var url = typeof fileUrlFn === 'function' ? fileUrlFn(path) : path;
    if (video.getAttribute('src') === url) {
      updateOverlays();
      syncTransport();
      return;
    }
    video.pause();
    video.src = url;
    video.load();
  }

  function refresh(opts) {
    opts = opts || {};
    var studio = $('layout-crop-studio');
    if (!studio) return;
    var sourcePath = opts.sourcePath || '';
    var show = !!sourcePath;
    // Studio stays visible whenever the dual-layout panel is open and a video exists.
    studio.classList.toggle('hidden', !show);
    if (!show) return;
    setVideoSrc($('layout-source-video'), sourcePath, opts.fileUrl);
    syncSliders();
    updateOverlays();
    syncTransport();
  }

  function getCrops() {
    syncHidden();
    return { game_crop: { ...gameCrop }, cam_crop: { ...camCrop } };
  }

  function onSlider(which) {
    if (which === 'game') {
      gameCrop.w = (Number($('layout-game-w').value) || 100) / 100;
      gameCrop.h = (Number($('layout-game-h').value) || 70) / 100;
      gameCrop = clampCrop(gameCrop);
    } else {
      camCrop.w = (Number($('layout-cam-w').value) || 28) / 100;
      camCrop.h = (Number($('layout-cam-h').value) || 28) / 100;
      camCrop = clampCrop(camCrop);
    }
    updateOverlays();
  }

  function bindTransport() {
    var video = $('layout-source-video');
    if (!video || video.dataset.transportBound === '1') return;
    video.dataset.transportBound = '1';

    $('layout-play-toggle')?.addEventListener('click', function () {
      if (video.paused) video.play().catch(function () {});
      else video.pause();
      syncTransport();
    });
    $('layout-seek-back')?.addEventListener('click', function () {
      video.currentTime = Math.max(0, (video.currentTime || 0) - 10);
      syncTransport();
      updateOverlays();
    });
    $('layout-seek-fwd')?.addEventListener('click', function () {
      var dur = isFinite(video.duration) ? video.duration : 0;
      video.currentTime = Math.min(dur || 1e9, (video.currentTime || 0) + 10);
      syncTransport();
      updateOverlays();
    });
    var seek = $('layout-seek');
    seek?.addEventListener('input', function () {
      video.currentTime = Number(seek.value) || 0;
      syncTransport();
    });
    seek?.addEventListener('change', function () {
      updateOverlays();
    });
    video.addEventListener('loadedmetadata', function () {
      syncTransport();
      updateOverlays();
    });
    video.addEventListener('timeupdate', function () {
      syncTransport();
      drawResultPreview();
    });
    video.addEventListener('play', function () {
      syncTransport();
      startPreviewLoop();
    });
    video.addEventListener('pause', function () {
      syncTransport();
      stopPreviewLoop();
      drawResultPreview();
    });
    video.addEventListener('ended', function () {
      video.pause();
      syncTransport();
    });
  }

  var previewRaf = 0;
  function startPreviewLoop() {
    stopPreviewLoop();
    function tick() {
      drawResultPreview();
      previewRaf = requestAnimationFrame(tick);
    }
    previewRaf = requestAnimationFrame(tick);
  }
  function stopPreviewLoop() {
    if (previewRaf) cancelAnimationFrame(previewRaf);
    previewRaf = 0;
  }

  function bind() {
    if (bound) return;
    bound = true;
    bindDrag('layout-game-overlay', 'game');
    bindDrag('layout-cam-overlay', 'cam');
    bindTransport();
    ['layout-game-w', 'layout-game-h'].forEach(function (id) {
      $(id)?.addEventListener('input', function () { onSlider('game'); });
    });
    ['layout-cam-w', 'layout-cam-h'].forEach(function (id) {
      $(id)?.addEventListener('input', function () { onSlider('cam'); });
    });
    [
      'process-layout', 'process-cam-split', 'process-stacked-side',
      'process-cam-scale', 'process-cam-position',
    ].forEach(function (id) {
      var el = $(id);
      if (!el) return;
      el.addEventListener('change', drawResultPreview);
      el.addEventListener('input', drawResultPreview);
    });
    $('layout-source-video')?.addEventListener('loadedmetadata', updateOverlays);
    window.addEventListener('resize', updateOverlays);
    syncHidden();
  }

  root.EddLayoutCrop = {
    bind: bind,
    refresh: refresh,
    getCrops: getCrops,
    updateOverlays: updateOverlays,
    drawResultPreview: drawResultPreview,
  };
})(typeof window !== 'undefined' ? window : this);
