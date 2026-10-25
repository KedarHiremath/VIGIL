"""Domain schemas and coordinate validation for visual evidence and bounding boxes."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


def validate_coordinates(raw_box: Any) -> tuple[float, float, float, float] | None:
    """Validate and normalize 2D bounding box coordinates.

    Expected format: normalized [x_min, y_min, x_max, y_max] where each value
    is in [0.0, 1.0]. Rejects non-numeric, infinite, out-of-bounds, or inverted boxes.
    """
    coords: list[float] = []

    if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
        for val in raw_box:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                return None
            f_val = float(val)
            if not math.isfinite(f_val):
                return None
            coords.append(f_val)
    elif isinstance(raw_box, dict):
        # Support dict formats like {"x_min": ..., "y_min": ..., "x_max": ..., "y_max": ...}
        # or {"xmin": ..., "ymin": ..., "xmax": ..., "ymax": ...}
        x1 = raw_box.get("x_min", raw_box.get("xmin"))
        y1 = raw_box.get("y_min", raw_box.get("ymin"))
        x2 = raw_box.get("x_max", raw_box.get("xmax"))
        y2 = raw_box.get("y_max", raw_box.get("ymax"))
        if any(v is None for v in (x1, y1, x2, y2)):
            return None
        for val in (x1, y1, x2, y2):
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                return None
            f_val = float(val)
            if not math.isfinite(f_val):
                return None
            coords.append(f_val)
    else:
        return None

    x_min, y_min, x_max, y_max = coords[0], coords[1], coords[2], coords[3]

    # Handle scale if 0-1000 scale was returned by vision model
    if all(v > 1.0 and v <= 1000.0 for v in (x_min, y_min, x_max, y_max)):
        x_min /= 1000.0
        y_min /= 1000.0
        x_max /= 1000.0
        y_max /= 1000.0

    # Strict bounds check [0.0, 1.0]
    if not (0.0 <= x_min < x_max <= 1.0 and 0.0 <= y_min < y_max <= 1.0):
        return None

    # Minimum bounding box span (0.5% of dimension) to reject collapsed boxes
    if (x_max - x_min) < 0.005 or (y_max - y_min) < 0.005:
        return None

    return (round(x_min, 4), round(y_min, 4), round(x_max, 4), round(y_max, 4))


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates and object properties."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)
    label: str = Field(min_length=1)
    category: str = Field(default="object")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    entity_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    valid: bool = True


class VisualEvidenceItem(BaseModel):
    """Forensic visual evidence item linking an image frame to bounding boxes and report tags."""

    artifact_id: str = Field(description="Original frame artifact ID")
    annotated_artifact_id: str | None = Field(
        default=None, description="Artifact ID of model-annotated derivative"
    )
    storage_uri: str = Field(
        description="Display URI (annotated derivative if available, else original)"
    )
    original_storage_uri: str = Field(description="Storage URI of original unannotated frame")
    media_asset_id: str | None = None
    camera_id: str | None = None
    camera_label: str | None = None
    timestamp_seconds: float | None = None
    caption: str = Field(default="Salient incident visual evidence.")
    tags: list[str] = Field(default_factory=list)
    resolved_entity_ids: list[str] = Field(default_factory=list)
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)
    has_overlay: bool = False
    disclaimer: str = (
        "Model-generated overlay: Bounding boxes and labels are AI-generated and require human verification."
    )
