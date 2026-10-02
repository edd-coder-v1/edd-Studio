# Third-party components

This file identifies components relevant to this branch. It is not a complete
license bundle for a self-contained installer. Preserve the actual notices and
license files belonging to every artifact included in a release.

## Bundled YuNet models

Copyright (c) 2020 Shiqi Yu. MIT License. The complete upstream license is included
at `server/assets/yunet/LICENSE`. Source repository:
https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet

| File | SHA-256 |
| --- | --- |
| face_detection_yunet_2023mar.onnx | 8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 |
| face_detection_yunet_2026may.onnx | ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0 |

OpenCV 4 uses the 2023 model; OpenCV 5 uses the dynamic-shape 2026 model.
The upstream model directory identifies its files as MIT licensed:
https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md

## External dependencies and release checks

- OpenCV 4.5+ source is Apache-2.0. Wheels also include native libraries with
  separate notices; retain `LICENSE.txt` and `LICENSE-3RD-PARTY.txt` from the exact
  wheel. https://opencv.org/license/
- FFmpeg licensing depends on build flags and linked libraries. Current export
  paths use libx264. Do not label an arbitrary FFmpeg build LGPL-only or redistribute
  it without its corresponding notices/source obligations being addressed.
  https://ffmpeg.org/legal.html
- PyAV and OpenCV can carry additional FFmpeg libraries independently of the
  command-line executable. Audit those artifacts separately.
- Ultralytics is no longer a default requirement. Its optional legacy backend
  needs its own AGPL/commercial-license review; bundled YuNet does not settle the
  obligations of an existing Ultralytics installation.
- Qwen2.5 3B uses the Qwen Research license, not the Apache license used by some
  other sizes. Review model-specific terms and revisions before selecting or
  distributing weights. https://huggingface.co/Qwen/Qwen2.5-3B/blob/main/LICENSE
- Electron, Chromium, Python wheels, fonts, and other assets require notices from
  the exact release artifacts. No general family label replaces that inventory.

Do not publish a self-contained release using this inventory alone. Complete the
artifact-specific license collection, model inventory, dependency lock and
clean-machine installer checks first.
