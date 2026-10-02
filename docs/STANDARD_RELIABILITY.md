# Standard reliability and multicamera

This development branch adds project backup/import/relink controls, last-good
local project records, persistent processing recovery records, a shared heavy-job
slot, cut timing maps, clean cut sources for caption revisions, XML escaping,
and a local two/three-camera workspace. These features do not require a Premium
edition. No release has been published from this branch.

## Try multicamera

1. Restart the development app and open **Multicamera** in the sidebar.
2. Choose two or three recordings of the same event with shared audio, or open
   a saved `.klipzy-multicam.json` sequence.
3. Set a short test range and choose **Sync and suggest shots**.
4. Review offsets and shot previews. Change cameras, split/merge shots, or adjust
   boundaries. Camera time equals sequence time plus its offset.
5. Save a sequence file, select an export folder and size, confirm review, and
   export. The export includes continuous audio from camera 1.

Pacing mode suggests cuts near quieter moments and alternates available angles.
The optional speaker mode is described below. Sync searches within 30 seconds;
weak matches and detected drift require manual review. It checks the beginning
and ending audio windows but does not correct clock drift. All cameras must
overlap the requested range. Each export writes a new MP4 and a sequence JSON.
Cancel removes temporary render files; original recordings remain untouched.

## Test Follow speakers

Speaker mode is an experimental, local voice-grouping workflow. It does not
recognize names, infer which person is in an angle, or guarantee separation of
overlapping voices. Choose the number of voices actually speaking in the test
range; forcing too many groups can split one voice into multiple labels.

After the base requirements, install the optional packages with:
`python -m pip install --no-deps -r requirements-speakers.txt`.
They are installed in the development environment used for this work. The
WebRTC wheel supplies the `webrtcvad` module; upstream Resemblyzer metadata
names the older source distribution, so dependency checkers may flag that
metadata mismatch. No Hugging Face token or cloud transcription is needed.

1. Select **Follow speakers (experimental)** and the expected voice count.
2. Analyze 60–120 seconds initially (maximum 30 minutes per speaker test).
3. **Preview voice** for each group, then assign its preferred camera. You can
   assign several speakers to the same wide angle.
4. Expand **Review and correct speaker turns**. Listen to each turn and correct
   its voice label or mark it uncertain. Timings use camera 1's source timeline.
5. Choose a **Wide fallback** and a minimum shot length (try 3 seconds).
6. **Apply speaker choices**, review the resulting cuts, then confirm and export.

Uncertain, non-speech and unmapped turns request the wide angle, subject to
minimum-shot holds. Brief changes are suppressed to avoid rapid camera flicker.
Long speaker turns stay on their assigned camera; target pacing length is used
by pacing mode only. Mapping/turn changes require Apply again. Coverage is the
fraction of time assigned a voice label, **not** a recognition accuracy score.
The implementation uses overlapping two-second voice windows and one-second
decisions; short interruptions and speech overlaps can be missed.

Validation on two 60-second interview samples completed local analysis and
720p export with continuous audio. Suggested-label coverage was 38.3% and 90%.
Test camera assignments were illustrative, not manually verified speaker/person
matches. Human review of the saved voice samples is still required.

## Projects and cuts

Project safety controls are on Projects. Backup files contain settings and
paths, not the video itself. Import merges readable projects and gives collisions
new IDs. An unreadable primary record falls back to the last-good local backup;
if both fail, saving is blocked until a backup is imported. Relinking assumes
the replacement is the same recording with the same timeline.

Filler/silence cuts retain the previous clip state for Undo, remap words, and
regenerate subtitle sidecars. When a clean source exists, a separate clean cut
is rendered so captions can be revised. Previously burned text cannot be removed
from a recording that already contains it. Sidecar failure is reported without
discarding the cut. Recovery restarts interrupted processing from the beginning;
it is not a resumable mid-model checkpoint.

## Vision and privacy

The default face detector is bundled YuNet through OpenCV on CPU. Model checksums
are checked before use. Faces can be missed in distant, occluded or profile views;
framing still needs review. Existing motion-based crop heuristics are not verified
speaker identification. Legacy YOLO requires `requirements-yolo.txt`, existing
local weights and `KLIPZY_VISION_BACKEND=yolo`. Existing installations are not
uninstalled by this change.

The server disables supported dependency telemetry flags before model imports.
This does not make every feature offline: explicit installs/model downloads,
URL import, and user-configured remote engines can still use the network.
Multicamera analysis and rendering do not send footage to a service.

## Verification and remaining release work

Run `python -m pytest --rootdir=. --confcutdir=. checks -q` and
`node --test checks/*.test.cjs`. The local extended suites remain under `tests/`
and `ui/test/`. OpenCV and FFmpeg are needed for media validation.

The Electron launcher now recognizes a staged Windows runtime and uses the
user-data directory for packaged logs/outputs. A portable runtime has **not**
been assembled or tested on a clean machine. FFmpeg/PyAV binary provenance,
exact dependency locks and complete binary license bundles remain release work;
these changes are not a distribution approval. See THIRD-PARTY-NOTICES.md.

The single-clip editor explicitly rejects multiple source clips instead of
silently dropping them. Use the separate Multicamera workspace for sequencing.
Full timeline sequencing, automatic visual speaker-to-camera matching, drift correction, and
automatic visual-quality selection are future work.

## Public UI status

Multicamera is hidden and does not initialize in the public UI while separate development continues. Its existing code and backend routes remain available for development. To work on its UI locally, change MULTICAMERA_ENABLED in ui/src/multicam.js; leave it false for the current Standard interface.
