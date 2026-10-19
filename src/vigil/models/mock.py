"""High-fidelity mock LLM client for testing and offline forensic analysis."""

import json

from vigil.models.base import BaseLLMClient, LLMResponse


class MockLLMClient(BaseLLMClient):
    """Deterministic and context-aware mock LLM for offline development and testing."""

    def __init__(self, model_name: str = "mock-forensic-model") -> None:
        self.model_name = model_name
        self.call_count = 0

    def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.call_count += 1
        prompt_lower = prompt.lower()

        if "plan" in prompt_lower or "strategy" in prompt_lower:
            response_obj = {
                "phases": [
                    {
                        "phase_name": "frame_sampling",
                        "objective": "Extract key frames and interval samples",
                        "sample_rate_seconds": 2.0,
                    },
                    {
                        "phase_name": "visual_detection",
                        "objective": "Detect persons, vehicles, and objects",
                    },
                    {
                        "phase_name": "event_correlation",
                        "objective": "Synthesize chronological events and link occurrences",
                    },
                    {
                        "phase_name": "evidence_assessment",
                        "objective": "Assess evidence quality and uncertainty",
                    },
                    {
                        "phase_name": "report_generation",
                        "objective": "Generate final forensic findings report",
                    },
                ]
            }
        elif "report" in prompt_lower or "summary" in prompt_lower:
            response_obj = {
                "title": "Forensic Video Analysis Findings",
                "summary": (
                    "Forensic examination identified unauthorized individual entry at the perimeter "
                    "followed by vehicle arrival. High quality evidence with verified timestamps."
                ),
                "key_findings": [
                    "Unauthorized subject entered through perimeter gate.",
                    "White sedan observed in perimeter zone at t=14.0s.",
                ],
            }
        elif "correlat" in prompt_lower or "event" in prompt_lower:
            response_obj = {
                "events": [
                    {
                        "event_type": "restricted_area_entry",
                        "description": "Subject observed entering restricted area.",
                        "confidence": 0.92,
                    }
                ],
                "links": [
                    {
                        "relationship_type": "before",
                        "rationale": "Perimeter breach observed prior to vehicle arrival.",
                        "confidence": 0.88,
                    }
                ],
            }
        elif "assess" in prompt_lower:
            response_obj = {
                "rating": "high",
                "assessment_type": "evidence_quality",
                "rationale": "High resolution visual evidence with clear unobstructed visibility.",
            }
        else:
            response_obj = {
                "findings": "Standard forensic detection completed.",
                "confidence": 0.85,
            }

        content = (
            json.dumps(response_obj)
            if json_mode
            else str(response_obj.get("summary", response_obj))
        )
        return LLMResponse(content=content, model_name=self.model_name)

    def analyze_image(
        self,
        prompt: str,
        image_data: str,
        mime_type: str = "image/jpeg",
        system_instruction: str | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        self.call_count += 1
        response_obj = {
            "observations": [
                {
                    "observation_type": "person_detection",
                    "description": "Adult male in dark jacket and denim trousers walking eastward.",
                    "confidence": 0.94,
                    "entity": {
                        "entity_type": "person",
                        "label": "Suspect-1",
                        "attributes": {
                            "clothing_upper": "dark jacket",
                            "clothing_lower": "denim trousers",
                        },
                    },
                },
                {
                    "observation_type": "vehicle_detection",
                    "description": "White 4-door sedan stationary near loading bay.",
                    "confidence": 0.89,
                    "entity": {
                        "entity_type": "vehicle",
                        "label": "Vehicle-1",
                        "attributes": {"color": "white", "vehicle_type": "sedan"},
                    },
                },
            ]
        }
        content = json.dumps(response_obj)
        return LLMResponse(content=content, model_name=self.model_name)
