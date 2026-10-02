# Investigation Workflow

```text
Many camera feeds / recorded footages (100+ cameras)
                    |
                    v
Ingest, preprocess, and index each camera's video
(frames, audio, detections, tracks, metadata, timestamps)
                    |
                    v
Build searchable temporal and spatial camera representation
                    |
                    v
Natural-language investigation query
(no incident timestamp is provided)
                    |
                    v
Agent searches candidate cameras and time windows
                    |
                    v
Retrieve relevant video segments
                    |
                    v
Detect and track entities/events; correlate evidence across cameras
                    |
                    v
Expand to adjacent cameras and earlier/later time windows when needed
                    |
                    v
Fuse visual, audio, metadata, and camera-topology evidence
                    |
                    v
Reconstruct incident timeline and cross-camera movement path
                    |
                    v
Estimate confidence and record uncertainty
                    |
                    v
Generate evidence-grounded report
(clips, camera IDs, timestamps, findings, and confidence)
```

The agent stops when evidence is sufficient for the query or when it can clearly report that the available footage is inconclusive.
