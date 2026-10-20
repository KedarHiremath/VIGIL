"""VIGIL tool worker implementations conforming to TaskWorker protocol."""

from vigil.tools.audio_transcriber import AudioTranscriberWorker
from vigil.tools.base import BaseToolWorker, generate_sha256
from vigil.tools.clip_slicer import ClipSlicerWorker
from vigil.tools.coverage_tracker import CoverageTrackerWorker
from vigil.tools.event_correlator import EventCorrelatorWorker
from vigil.tools.evidence_assessor import EvidenceAssessorWorker
from vigil.tools.frame_extractor import FrameExtractorWorker
from vigil.tools.media_ingestion import MediaIngestionWorker
from vigil.tools.report_generator import ReportGeneratorWorker
from vigil.tools.visual_detector import VisualDetectorWorker

__all__ = [
    "AudioTranscriberWorker",
    "BaseToolWorker",
    "ClipSlicerWorker",
    "CoverageTrackerWorker",
    "EventCorrelatorWorker",
    "EvidenceAssessorWorker",
    "FrameExtractorWorker",
    "MediaIngestionWorker",
    "ReportGeneratorWorker",
    "VisualDetectorWorker",
    "generate_sha256",
]
