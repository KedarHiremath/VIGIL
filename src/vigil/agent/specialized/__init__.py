"""Specialized forensic agents coordinating domain-specific tools."""

from vigil.agent.specialized.audio_agent import AudioAgent
from vigil.agent.specialized.correlation_agent import TemporalCorrelationAgent
from vigil.agent.specialized.report_writer_agent import ReportWriterAgent
from vigil.agent.specialized.verification_agent import EvidenceVerificationAgent
from vigil.agent.specialized.visual_agent import VisualAgent

__all__ = [
    "AudioAgent",
    "EvidenceVerificationAgent",
    "ReportWriterAgent",
    "TemporalCorrelationAgent",
    "VisualAgent",
]
