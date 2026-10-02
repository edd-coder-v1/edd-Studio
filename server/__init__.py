"""Package init for server."""

# Applied before third-party imports. Inference remains local; explicit model
# downloads and user-configured remote engines are separate, disclosed actions.
import os
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['SCARF_NO_ANALYTICS'] = 'true'
os.environ['PYANNOTE_METRICS_ENABLED'] = '0'
os.environ['YOLO_OFFLINE'] = 'true'

from server.models import (
    ClipCandidate, ClipResult, ProcessRequest, ProcessResponse,
    TranscriptSegment, WordTimestamp, ChatRequest, ChatResponse,
)

__all__ = [
    "ClipCandidate", "ClipResult", "ProcessRequest", "ProcessResponse",
    "TranscriptSegment", "WordTimestamp", "ChatRequest", "ChatResponse",
]
