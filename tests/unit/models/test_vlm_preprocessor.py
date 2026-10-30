"""Unit tests for Llama 3.2 Vision image preprocessor and Greedy Knapsack batcher."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from vigil.models.nvidia_nim import NvidiaNIMClient
from vigil.models.vlm_preprocessor import (
    GreedyKnapsackBatcher,
    ImageBatch,
    Llama32VisionPreprocessor,
    PreprocessedImage,
)
from VLM_Accelerator.knapsack import calculate_http_limits
from VLM_Accelerator.preprocessor import Llama32VisionPreprocessor as StandalonePreprocessor


def create_test_image(width: int, height: int, color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestLlama32VisionPreprocessor:
    def test_find_best_grid(self) -> None:
        pre = Llama32VisionPreprocessor()
        # Square image -> (1, 1)
        assert pre.find_best_grid(1000, 1000) == (1, 1)
        # 16:9 wide image -> (2, 1) [1120x560]
        assert pre.find_best_grid(1920, 1080) == (2, 1)
        # Tall portrait image -> (1, 2) [560x1120]
        assert pre.find_best_grid(1080, 1920) == (1, 2)

    def test_calculate_target_resolution_compact(self) -> None:
        pre = Llama32VisionPreprocessor()
        # 1080p in compact mode must fit inside 560x560
        target_size, grid = pre.calculate_target_resolution(1920, 1080, mode="compact")
        assert grid == (1, 1)
        assert target_size[0] == 560
        assert target_size[1] == 315

    def test_calculate_target_resolution_optimal(self) -> None:
        pre = Llama32VisionPreprocessor()
        # 1080p in optimal mode matches (2, 1) grid -> fits inside 1120x560
        target_size, grid = pre.calculate_target_resolution(1920, 1080, mode="optimal")
        assert grid == (2, 1)
        assert target_size[0] <= 1120
        assert target_size[1] <= 560

    def test_preprocess_image_bytes_and_tokens(self) -> None:
        pre = Llama32VisionPreprocessor()
        raw_jpeg = create_test_image(1920, 1080)
        orig_len = len(raw_jpeg)

        res = pre.preprocess_image(raw_jpeg, mode="compact", identifier="test_frame")
        assert res.identifier == "test_frame"
        assert res.processed_size == (560, 315)
        assert res.num_tiles == 1
        assert res.estimated_tokens == 1604  # 1600 + 4
        assert res.byte_size < orig_len
        assert res.base64_data != ""
        assert res.data_uri.startswith("data:image/jpeg;base64,")


class TestGreedyKnapsackBatcher:
    def test_knapsack_packs_within_byte_limit(self) -> None:
        pre = Llama32VisionPreprocessor()
        batcher = GreedyKnapsackBatcher(
            max_payload_bytes=100_000,
            headroom_bytes=0,
            max_items_per_batch=4,
        )

        items: list[PreprocessedImage] = []
        for i in range(8):
            data = create_test_image(800, 600)
            p = pre.preprocess_image(data, mode="compact", identifier=f"frame_{i}")
            items.append(p)

        batches = batcher.allocate_batches(items, strategy="first_fit_decreasing")
        assert len(batches) > 1

        for b in batches:
            assert b.total_wire_bytes <= 100_000
            assert len(b.images) <= 4

    def test_build_nim_multimodal_message(self) -> None:
        pre = Llama32VisionPreprocessor()
        batcher = GreedyKnapsackBatcher()

        p1 = pre.preprocess_image(create_test_image(200, 200), identifier="f1", timestamp_seconds=1.5)
        p2 = pre.preprocess_image(create_test_image(200, 200), identifier="f2", timestamp_seconds=3.0)

        batch = ImageBatch(batch_index=0)
        batch.add(p1)
        batch.add(p2)

        messages = batcher.build_nim_multimodal_message(
            prompt="Detect suspects",
            batch=batch,
            system_instruction="Forensic assistant",
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "Forensic assistant"
        assert messages[1]["role"] == "user"

        content = messages[1]["content"]
        assert content[0]["type"] == "text"
        assert "f1 at 1.5s" in content[0]["text"]
        assert content[1]["type"] == "image_url"
        assert content[2]["type"] == "image_url"


class TestNvidiaNIMClientBatching:
    @patch.object(NvidiaNIMClient, "_call_completions")
    def test_analyze_image_batch_dispatches_correctly(self, mock_call: MagicMock) -> None:
        from vigil.models.base import LLMResponse
        mock_call.return_value = LLMResponse(content="OK", model_name="vlm")

        client = NvidiaNIMClient(api_key="nvapi-test12345")
        frames = [create_test_image(400, 300) for _ in range(3)]

        responses = client.analyze_image_batch(
            prompt="Analyze frames",
            images=frames,
            shrink_mode="compact",
        )

        assert len(responses) >= 1
        assert mock_call.called
        assert responses[0].content == "OK"


class TestStandaloneAccelerator:
    def test_calculate_http_limits(self) -> None:
        limits = calculate_http_limits(gateway_limit_kb=180.0, headroom_kb=4.0)
        assert limits["usable_wire_bytes"] == 180224
        assert limits["max_context_tokens"] == 131072
        assert limits["max_images_per_request_compact"] >= 3

    def test_standalone_preprocessor(self) -> None:
        pre = StandalonePreprocessor()
        img_bytes = create_test_image(1280, 720)
        res = pre.preprocess(img_bytes, mode="compact")
        assert res.processed_size == (560, 315)
        assert res.num_tiles == 1
