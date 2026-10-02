# Project Objectives

Build an agentic multimodal video investigation system for large surveillance environments with 100+ cameras and many video footages. An investigator provides a natural-language query **without an incident timestamp**; the system discovers and reconstructs relevant incident(s).

## Objectives

1. **Ingest and index multi-camera video:** Process footage from many cameras and create searchable temporal, visual, audio, and camera-location indexes.
2. **Discover incidents without a known time:** Locate candidate cameras and time windows directly from the investigation query instead of requiring a supplied timestamp.
3. **Associate evidence across cameras:** Link the same person, object, or event across overlapping and adjacent camera views.
4. **Investigate selectively with an agent:** Choose which camera feeds, segments, and analysis tools to inspect next, avoiding exhaustive analysis of all footage.
5. **Correlate multimodal evidence:** Combine visual observations, tracking, audio cues, metadata, and camera relationships into consistent evidence.
6. **Reconstruct the incident:** Produce an ordered timeline and spatial path showing how relevant entities/events move across cameras.
7. **Generate evidence-grounded findings:** Report conclusions with supporting clips, timestamps, camera IDs, confidence, and stated uncertainty.
8. **Measure efficiency and reliability:** Compare selective agent-driven investigation with exhaustive or fixed-camera analysis using retrieval accuracy, association quality, reconstruction quality, and analysis cost/time.

## Scope Constraint

The system assists human investigation; it does not make final security, legal, or disciplinary decisions autonomously.
