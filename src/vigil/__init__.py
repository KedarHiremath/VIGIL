"""VIGIL: Agentic Video-Forensics System."""

import sys

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
from vigil.api import app, create_app
from vigil.config import VigilConfig, config
from vigil.services import InvestigationService, TelemetryManager
from vigil.storage.repository import InvestigationRepository


def main() -> None:
    """CLI entrypoint for VIGIL."""
    if len(sys.argv) > 1 and sys.argv[1] in {"serve", "api", "run"}:
        import uvicorn

        host = "0.0.0.0"
        port = 8000
        print(f"Starting VIGIL API server on {host}:{port}...")
        uvicorn.run("vigil.api.app:app", host=host, port=port, reload=False)
        return

    print("=================================================================")
    print("  VIGIL: Autonomous Video-Forensics Agentic System")
    print("=================================================================")
    print(f"Active LLM Provider: {config.llm_provider}")
    print(f"Storage Directory  : {config.storage_root}")
    print("Status             : Engine Ready")
    print("Run tests with     : pytest")
    print("Start API with     : vigil serve (or uvicorn vigil.api.app:app)")
    print("=================================================================")


__all__ = [
    "AgenticOrchestrator",
    "AudioAgent",
    "EvidenceVerificationAgent",
    "InvestigationOutcome",
    "InvestigationPlanner",
    "InvestigationRepository",
    "InvestigationService",
    "LeadInvestigatorAgent",
    "ReportWriterAgent",
    "TelemetryManager",
    "TemporalCorrelationAgent",
    "VigilConfig",
    "VisualAgent",
    "app",
    "config",
    "create_app",
    "create_default_executor",
    "main",
]
