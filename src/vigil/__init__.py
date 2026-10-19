"""VIGIL: Agentic Video-Forensics System."""

from vigil.agent import (
    AgenticOrchestrator,
    AudioAgent,
    EvidenceVerificationAgent,
    InvestigationOutcome,
    InvestigationPlanner,
    LeadInvestigatorAgent,
    ReportWriterAgent,
    TemporalCorrelationAgent,
    VisualAgent,
    create_default_executor,
)
from vigil.config import VigilConfig, config
from vigil.storage.repository import InvestigationRepository


def main() -> None:
    """CLI entrypoint for VIGIL."""
    print("=================================================================")
    print("  VIGIL: Autonomous Video-Forensics Agentic System")
    print("=================================================================")
    print(f"Active LLM Provider: {config.llm_provider}")
    print(f"Storage Directory  : {config.storage_root}")
    print("Status             : Engine Ready")
    print("Run tests with     : pytest")
    print("=================================================================")


__all__ = [
    "AgenticOrchestrator",
    "AudioAgent",
    "EvidenceVerificationAgent",
    "InvestigationOutcome",
    "InvestigationPlanner",
    "InvestigationRepository",
    "LeadInvestigatorAgent",
    "ReportWriterAgent",
    "TemporalCorrelationAgent",
    "VigilConfig",
    "VisualAgent",
    "config",
    "create_default_executor",
    "main",
]
