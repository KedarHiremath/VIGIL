"""VIGIL Media Ingestion, Indexing, and Forensic Processing Package."""

from vigil.media.decoder import DemuxedAudio, ExtractedFrame, MediaDecoder
from vigil.media.ingestion import IngestionResult, MediaIngestionService
from vigil.media.metadata import (
    MediaMetadata,
    MediaMetadataExtractor,
    extract_media_metadata,
)
from vigil.media.slicer import ClipSlicer, SliceResult

__all__ = [
    "ClipSlicer",
    "DemuxedAudio",
    "ExtractedFrame",
    "IngestionResult",
    "MediaDecoder",
    "MediaIngestionService",
    "MediaMetadata",
    "MediaMetadataExtractor",
    "SliceResult",
    "extract_media_metadata",
]
