"""Bundled MIT-licensed YuNet face detector; no runtime downloads/network.

See server/assets/yunet/LICENSE and SOURCE_COMMIT. This is a face-framing heuristic, not
speaker identification. Profile/occluded/small faces can be missed.
"""
from types import SimpleNamespace
from pathlib import Path
import hashlib

class Coordinates:
    def __init__(self, values): self.values=values
    def cpu(self): return self
    def numpy(self): return self.values
    def __getitem__(self, index): return self.values[index]

class LocalFaceDetector:
    def __init__(self):
        import cv2
        self.cv2=cv2
        modern=int(cv2.__version__.split('.')[0])>=5
        filename='face_detection_yunet_2026may.onnx' if modern else 'face_detection_yunet_2023mar.onnx'
        expected='ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0' if modern else '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
        model=Path(__file__).resolve().parents[1]/'assets'/'yunet'/filename
        if hashlib.sha256(model.read_bytes()).hexdigest()!=expected:raise RuntimeError('YuNet model checksum mismatch')
        self.detector=cv2.FaceDetectorYN.create(str(model),'',(320,320),.75,.3,5000)

    def __call__(self, frame, **kwargs):
        import numpy as np
        cv2=self.cv2
        height,width=frame.shape[:2]
        scale=min(1.,960/max(width,height))
        small=cv2.resize(frame,None,fx=scale,fy=scale) if scale<1 else frame
        self.detector.setInputSize((small.shape[1],small.shape[0]))
        _,faces=self.detector.detect(small)
        boxes=[]
        for face in ([] if faces is None else faces):
            x,y,w,h=face[:4]
            coords=np.asarray([x,y,x+w,y+h],dtype=float)/scale
            boxes.append(SimpleNamespace(xyxy=[Coordinates(coords)]))
        return [SimpleNamespace(boxes=boxes)]
