"""Worker registry bootstrap for TaskExecutor."""

from vigil.models.base import BaseLLMClient
from vigil.models.factory import get_llm_client
from vigil.orchestration.executor import TaskExecutor
from vigil.storage.repository import InvestigationRepository
from vigil.tools.audio_transcriber import AudioTranscriberWorker
from vigil.tools.clip_slicer import ClipSlicerWorker
from vigil.tools.coverage_tracker import CoverageTrackerWorker
from vigil.tools.event_correlator import EventCorrelatorWorker
from vigil.tools.evidence_assessor import EvidenceAssessorWorker
from vigil.tools.frame_extractor import FrameExtractorWorker
from vigil.tools.media_ingestion import MediaIngestionWorker
from vigil.tools.report_generator import ReportGeneratorWorker
from vigil.tools.visual_detector import VisualDetectorWorker


def create_default_executor(
    repository: InvestigationRepository,
    llm_client: BaseLLMClient | None = None,
) -> TaskExecutor:
    """Build and configure a TaskExecutor with all standard VIGIL forensic tool workers."""
    llm = llm_client or get_llm_client()
    executor = TaskExecutor()

    # Register each tool worker
    executor.register(
        "media_ingestion", MediaIngestionWorker(repository=repository, llm_client=llm)
    )
    executor.register(
        "frame_sampling", FrameExtractorWorker(repository=repository, llm_client=llm)
    )
    executor.register(
        "clip_extraction", FrameExtractorWorker(repository=repository, llm_client=llm)
    )
    executor.register(
        "clip_slicing", ClipSlicerWorker(repository=repository, llm_client=llm)
    )
    executor.register(
        "incident_clip_extraction",
        ClipSlicerWorker(repository=repository, llm_client=llm),
    )
    executor.register(
        "visual_analysis", VisualDetectorWorker(repository=repository, llm_client=llm)
    )
    executor.register(
        "audio_transcription",
        AudioTranscriberWorker(repository=repository, llm_client=llm),
    )
    executor.register(
        "event_correlation",
        EventCorrelatorWorker(repository=repository, llm_client=llm),
    )
    executor.register(
        "evidence_assessment",
        EvidenceAssessorWorker(repository=repository, llm_client=llm),
    )
    executor.register(
        "coverage_evaluation",
        CoverageTrackerWorker(repository=repository, llm_client=llm),
    )
    executor.register(
        "report_generation",
        ReportGeneratorWorker(repository=repository, llm_client=llm),
    )

    return executor
