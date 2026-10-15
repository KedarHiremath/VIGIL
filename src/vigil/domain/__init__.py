"""VIGIL domain schemas."""

from vigil.domain.coverage import CoverageRecord, CoverageStatus
from vigil.domain.investigation import Investigation
from vigil.domain.report import Report

__all__ = [
    # Keep all existing exported names here.
    "CoverageRecord",
    "CoverageStatus",
    "Investigation",
    "Report",
]
