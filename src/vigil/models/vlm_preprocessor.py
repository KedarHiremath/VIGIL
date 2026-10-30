"""Meta / Llama 3.2 11B Vision Instruct Image Preprocessor & Greedy Knapsack Batcher.

Optimised for build.nvidia NIM endpoints:
- Matches Llama 3.2 Vision's native vision encoder input structure:
    * Tile resolution: 560x560 px
    * Patch size: 14x14 px
    * Supported aspect ratio grids: (1,1), (1,2), (2,1), (2,2) [max 4 tiles]
    * Tokens per tile: 1,600 visual tokens (+ global/separator tokens)
- Enforces build.nvidia inline payload limits:
    * Inline Base64 Data URI ceiling: ~180 KB (184,320 bytes) safe limit
    * Context limit: 131,072 tokens
- Provides Greedy Knapsack (Bin-Packing) allocation to pack multiple pre-shrunk
  frames into the minimum number of HTTP requests without exceeding gateway limits.
"""

from __future__ import annotations

import base64
import io
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlparse

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & Defaults
# ---------------------------------------------------------------------------

# Llama 3.2 Vision encoder specifications
LLAMA_TILE_SIZE = 560  # 560x560 pixels per tile
LLAMA_PATCH_SIZE = 14  # 14x14 pixels per patch -> (560/14)^2 = 1600 patches
LLAMA_TOKENS_PER_TILE = 1600
LLAMA_MAX_TILES = 4
LLAMA_ASPECT_RATIOS = (
    (1, 1),  # 560x560   (1 tile  -> 1600 tokens)
    (1, 2),  # 560x1120  (2 tiles -> 3200 tokens, tall/portrait)
    (2, 1),  # 1120x560  (2 tiles -> 3200 tokens, wide/16:9 landscape)
    (2, 2),  # 1120x1120 (4 tiles -> 6400 tokens, high-res quad)
)

# NVIDIA NIM / build.nvidia HTTP limits
# Inline base64 payload size threshold on integrate.api.nvidia.com / ai.api.nvidia.com:
# NVIDIA NIM gateway rejects inline payloads > 180KB-200KB with 413 / size rejection.
NVIDIA_INLINE_PAYLOAD_LIMIT_BYTES = 184_320  # 180 KB safe threshold
NVIDIA_PAYLOAD_HEADROOM_BYTES = 4_096        # Room for JSON headers, prompt, role tags
NVIDIA_MAX_CONTEXT_TOKENS = 131_072          # 128K context window


@dataclass(frozen=True)
class PreprocessedImage:
    """An image processed to match Llama 3.2 Vision's exact encoding requirements."""

    original_size: tuple[int, int]
    processed_size: tuple[int, int]
    tile_grid: tuple[int, int]
    num_tiles: int
    estimated_tokens: int
    raw_bytes: bytes
    base64_data: str
    byte_size: int
    base64_size: int
    mime_type: str = "image/jpeg"
    identifier: str = ""
    timestamp_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def data_uri(self) -> str:
        return f"data:{self.mime_type};base64,{self.base64_data}"

    @property
    def total_wire_cost_bytes(self) -> int:
        """Estimated wire cost in JSON payload including quotes and URI prefix."""
        # 'data:image/jpeg;base64,' is 23 bytes + JSON wrapper quotes & keys ~ 80 bytes
        return self.base64_size + len(self.mime_type) + 40


@dataclass
class ImageBatch:
    """A collection of preprocessed images greedily packed to fit in one HTTP request."""

    batch_index: int
    images: list[PreprocessedImage] = field(default_factory=list)
    total_wire_bytes: int = 0
    total_tokens: int = 0

    def add(self, item: PreprocessedImage) -> None:
        self.images.append(item)
        self.total_wire_bytes += item.total_wire_cost_bytes
        self.total_tokens += item.estimated_tokens

    def can_fit(
        self,
        item: PreprocessedImage,
        max_bytes: int,
        max_tokens: int,
        max_items: int = 16,
    ) -> bool:
        if len(self.images) >= max_items:
            return False
        if (self.total_wire_bytes + item.total_wire_cost_bytes) > max_bytes:
            return False
        if (self.total_tokens + item.estimated_tokens) > max_tokens:
            return False
        return True


# ---------------------------------------------------------------------------
# Preprocessor
# ---------------------------------------------------------------------------

class Llama32VisionPreprocessor:
    """Resizes and compresses images to the exact vision-encoder format of Llama 3.2 11B Vision.

    In Llama 3.2 Vision, images are partitioned into tiles of 560x560.
    The processor selects an aspect-ratio grid from {(1,1), (1,2), (2,1), (2,2)}.
    Pre-shrinking to this target resolution before Base64 serialization:
      1. Slashes network payload by 85-95% (e.g. 500KB -> 30KB).
      2. Ensures images fit within build.nvidia's 180 KB inline base64 ceiling.
      3. Avoids redundant server-side image downscaling.
      4. Keeps visual detail aligned with the model's 14x14 patch token grid.
    """

    def __init__(
        self,
        tile_size: int = LLAMA_TILE_SIZE,
        max_tiles: int = LLAMA_MAX_TILES,
        default_quality: int = 85,
    ) -> None:
        self.tile_size = tile_size
        self.max_tiles = max_tiles
        self.default_quality = default_quality

    def find_best_grid(
        self,
        width: int,
        height: int,
        max_tiles: int | None = None,
    ) -> tuple[int, int]:
        """Find the optimal (width_tiles, height_tiles) grid layout for an aspect ratio.

        Minimizes scale distortion and unnecessary padding while staying <= max_tiles.
        """
        allowed_tiles = max_tiles or self.max_tiles
        aspect_ratio = width / height

        best_grid = (1, 1)
        best_error = float("inf")

        for w_grid, h_grid in LLAMA_ASPECT_RATIOS:
            if w_grid * h_grid > allowed_tiles:
                continue
            grid_ar = (w_grid * self.tile_size) / (h_grid * self.tile_size)
            # Log-scale difference measures aspect ratio preservation symmetrically
            error = abs(math.log(aspect_ratio / grid_ar))
            if error < best_error:
                best_error = error
                best_grid = (w_grid, h_grid)

        return best_grid

    def calculate_target_resolution(
        self,
        width: int,
        height: int,
        mode: str = "optimal",
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Calculate target (new_width, new_height) and (grid_w, grid_h).

        Modes:
          - "compact": Fits into a single 560x560 tile (1 tile = 1600 tokens, ~25-35KB).
                       Best for packing many video frames into a single HTTP request.
          - "optimal": Chooses the best 1-4 tile grid matching the aspect ratio.
                       Best for high-detail forensic tasks (reads license plates/fine text).
        """
        if mode == "compact":
            grid = (1, 1)
            canvas_w = self.tile_size
            canvas_h = self.tile_size
        else:
            grid = self.find_best_grid(width, height, max_tiles=self.max_tiles)
            canvas_w = grid[0] * self.tile_size
            canvas_h = grid[1] * self.tile_size

        scale = min(canvas_w / width, canvas_h / height)
        # Never upscale beyond original dimensions
        scale = min(scale, 1.0)
        new_w = max(1, int(round(width * scale)))
        new_h = max(1, int(round(height * scale)))

        return (new_w, new_h), grid

    def preprocess_image(
        self,
        image_input: str | Path | bytes | Image.Image,
        mode: str = "optimal",
        quality: int | None = None,
        identifier: str = "",
        timestamp_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PreprocessedImage:
        """Shrink an image according to Llama 3.2 Vision requirements and encode to JPEG.

        Args:
            image_input: File path, file:// URI, raw bytes, base64 string, or PIL Image.
            mode: "compact" (1-tile / 560px max) or "optimal" (multi-tile up to 1120px).
            quality: JPEG compression quality (default 85).
            identifier: Optional label/name (e.g. frame_0042.jpg).
            timestamp_seconds: Video timestamp in seconds if applicable.
            metadata: Custom attributes.

        Returns:
            PreprocessedImage with exact dimensions, tile count, token estimate, and base64.
        """
        pil_img, resolved_id = self._load_pil_image(image_input)
        if not identifier:
            identifier = resolved_id

        orig_w, orig_h = pil_img.size
        target_size, grid = self.calculate_target_resolution(orig_w, orig_h, mode=mode)
        num_tiles = grid[0] * grid[1]
        # Llama 3.2 Vision uses 1600 tokens per tile + 4 global/framing tokens
        est_tokens = (num_tiles * LLAMA_TOKENS_PER_TILE) + 4

        # Convert to RGB if needed (handling RGBA, paletted, greyscale)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        # High-quality Lanczos resampling
        if target_size != (orig_w, orig_h):
            resized_img = pil_img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            resized_img = pil_img

        # Save to optimized JPEG bytes
        q = quality if quality is not None else self.default_quality
        buf = io.BytesIO()
        resized_img.save(
            buf,
            format="JPEG",
            quality=q,
            optimize=True,
            subsampling=0,  # 4:4:4 or 4:2:0 depending on PIL; 0 retains best chroma
        )
        raw_bytes = buf.getvalue()
        b64_str = base64.b64encode(raw_bytes).decode("utf-8")

        return PreprocessedImage(
            original_size=(orig_w, orig_h),
            processed_size=target_size,
            tile_grid=grid,
            num_tiles=num_tiles,
            estimated_tokens=est_tokens,
            raw_bytes=raw_bytes,
            base64_data=b64_str,
            byte_size=len(raw_bytes),
            base64_size=len(b64_str),
            mime_type="image/jpeg",
            identifier=identifier,
            timestamp_seconds=timestamp_seconds,
            metadata=metadata or {},
        )

    def _load_pil_image(
        self,
        image_input: str | Path | bytes | Image.Image,
    ) -> tuple[Image.Image, str]:
        """Resolve various input types into a PIL Image and identifier."""
        if isinstance(image_input, Image.Image):
            return image_input, "pil_image"

        if isinstance(image_input, (bytes, bytearray)):
            return Image.open(io.BytesIO(image_input)), "raw_bytes"

        if isinstance(image_input, (str, Path)):
            s = str(image_input).strip()
            if s.startswith("file://"):
                parsed = urlparse(s)
                path_str = unquote(parsed.path)
                if path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
                    path_str = path_str[1:]
                p = Path(path_str)
                if not p.is_file():
                    raise FileNotFoundError(f"Image not found at URI: {s}")
                return Image.open(p), p.name

            p = Path(s)
            if p.is_file():
                return Image.open(p), p.name

            # Check if it is a data URI or base64 string
            if s.startswith("data:image"):
                comma = s.find(",")
                if comma != -1:
                    s = s[comma + 1:]
            try:
                decoded = base64.b64decode(s)
                return Image.open(io.BytesIO(decoded)), "base64_string"
            except Exception as exc:
                raise ValueError(f"Could not load image from input '{s[:60]}...': {exc}") from exc

        raise TypeError(f"Unsupported image input type: {type(image_input)}")


# ---------------------------------------------------------------------------
# Greedy Knapsack Batcher
# ---------------------------------------------------------------------------

class GreedyKnapsackBatcher:
    """Greedily allocates preprocessed images into requests to maximize throughput.

    Solves the Multi-Capacity Bin Packing / Knapsack problem:
    - Primary constraint: HTTP request body Base64 wire size <= max_bytes (180KB safe limit).
    - Secondary constraint: Total estimated visual + prompt tokens <= max_tokens (131K context).
    - Tertiary constraint: Max items per batch (e.g. 8-16 frames).

    Uses First-Fit Decreasing (FFD) or Next-Fit heuristic to pack images greedily,
    ensuring no individual request violates the build.nvidia NIM inline payload limit.
    """

    def __init__(
        self,
        max_payload_bytes: int = NVIDIA_INLINE_PAYLOAD_LIMIT_BYTES,
        headroom_bytes: int = NVIDIA_PAYLOAD_HEADROOM_BYTES,
        max_context_tokens: int = NVIDIA_MAX_CONTEXT_TOKENS,
        max_items_per_batch: int = 12,
    ) -> None:
        self.max_payload_bytes = max_payload_bytes - headroom_bytes
        self.max_context_tokens = max_context_tokens
        self.max_items_per_batch = max_items_per_batch

    def allocate_batches(
        self,
        items: Sequence[PreprocessedImage],
        strategy: str = "first_fit_decreasing",
    ) -> list[ImageBatch]:
        """Greedily pack preprocessed images into batches.

        Args:
            items: Sequence of PreprocessedImage objects.
            strategy: "first_fit_decreasing" (packs most efficiently) or
                      "sequential" (maintains temporal video order).

        Returns:
            List of ImageBatch objects, each ready to be sent as one HTTP request.
        """
        if not items:
            return []

        batches: list[ImageBatch] = []

        if strategy == "first_fit_decreasing":
            # Sort descending by wire cost to optimize packing density
            sorted_items = sorted(items, key=lambda x: x.total_wire_cost_bytes, reverse=True)
            for item in sorted_items:
                placed = False
                for batch in batches:
                    if batch.can_fit(
                        item,
                        max_bytes=self.max_payload_bytes,
                        max_tokens=self.max_context_tokens,
                        max_items=self.max_items_per_batch,
                    ):
                        batch.add(item)
                        placed = True
                        break
                if not placed:
                    new_b = ImageBatch(batch_index=len(batches))
                    new_b.add(item)
                    batches.append(new_b)
        else:
            # Sequential (preserve temporal frame order)
            current_batch = ImageBatch(batch_index=0)
            for item in items:
                if current_batch.can_fit(
                    item,
                    max_bytes=self.max_payload_bytes,
                    max_tokens=self.max_context_tokens,
                    max_items=self.max_items_per_batch,
                ):
                    current_batch.add(item)
                else:
                    if current_batch.images:
                        batches.append(current_batch)
                    current_batch = ImageBatch(batch_index=len(batches))
                    current_batch.add(item)
            if current_batch.images:
                batches.append(current_batch)

        return batches

    @staticmethod
    def build_nim_multimodal_message(
        prompt: str,
        batch: ImageBatch,
        system_instruction: str | None = None,
    ) -> list[dict[str, Any]]:
        """Construct the OpenAI/NIM chat completions messages payload for a batch of images.

        Tags each image with its index, timestamp, and identifier so the VLM can refer
        to each image accurately in its response.
        """
        messages: list[dict[str, Any]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        content_parts: list[dict[str, Any]] = []

        # Add header prompt text
        img_manifest_lines = []
        for idx, img in enumerate(batch.images, start=1):
            ts_info = f" at {img.timestamp_seconds:.1f}s" if img.timestamp_seconds is not None else ""
            img_manifest_lines.append(f"Image {idx}: [{img.identifier}{ts_info}]")
        manifest_text = "\n".join(img_manifest_lines)

        full_prompt = (
            f"{prompt}\n\n"
            f"Images in this request ({len(batch.images)} total):\n"
            f"{manifest_text}\n\n"
            "Analyze each image individually and refer to it by its Image number and identifier."
        )
        content_parts.append({"type": "text", "text": full_prompt})

        # Add image URLs
        for idx, img in enumerate(batch.images, start=1):
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": img.data_uri,
                    },
                }
            )

        messages.append({"role": "user", "content": content_parts})
        return messages
