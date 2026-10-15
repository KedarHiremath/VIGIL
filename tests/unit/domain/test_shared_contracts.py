"""Tests for reusable VIGIL domain contract types."""

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from vigil.domain.common import (
    ConfidenceScore,
    Identifier,
    ReferenceIds,
    Timestamp,
)


def test_identifier_accepts_nonblank_string() -> None:
    adapter = TypeAdapter(Identifier)

    assert adapter.validate_python("media-001") == "media-001"


def test_identifier_strips_surrounding_whitespace() -> None:
    adapter = TypeAdapter(Identifier)

    assert adapter.validate_python("  media-001  ") == "media-001"


def test_identifier_rejects_blank_string() -> None:
    adapter = TypeAdapter(Identifier)

    with pytest.raises(ValidationError):
        adapter.validate_python("   ")


def test_timestamp_accepts_timezone_aware_datetime() -> None:
    adapter = TypeAdapter(Timestamp)
    value = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)

    assert adapter.validate_python(value) == value


def test_timestamp_rejects_naive_datetime() -> None:
    adapter = TypeAdapter(Timestamp)
    value = datetime(2026, 10, 15, 9, 0)

    with pytest.raises(ValidationError):
        adapter.validate_python(value)


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
def test_confidence_accepts_values_in_range(value: float) -> None:
    adapter = TypeAdapter(ConfidenceScore)

    assert adapter.validate_python(value) == value


@pytest.mark.parametrize("value", [-0.1, 1.1, float("inf"), float("nan")])
def test_confidence_rejects_invalid_values(value: float) -> None:
    adapter = TypeAdapter(ConfidenceScore)

    with pytest.raises(ValidationError):
        adapter.validate_python(value)


def test_reference_ids_accept_unique_values() -> None:
    adapter = TypeAdapter(ReferenceIds)

    assert adapter.validate_python(["media-001", "media-002"]) == [
        "media-001",
        "media-002",
    ]


def test_reference_ids_reject_duplicates() -> None:
    adapter = TypeAdapter(ReferenceIds)

    with pytest.raises(ValidationError):
        adapter.validate_python(["media-001", "media-001"])


def test_reference_ids_reject_blank_values() -> None:
    adapter = TypeAdapter(ReferenceIds)

    with pytest.raises(ValidationError):
        adapter.validate_python(["media-001", "   "])


def test_reference_ids_reject_duplicates_after_normalization() -> None:
    adapter = TypeAdapter(ReferenceIds)

    with pytest.raises(ValidationError):
        adapter.validate_python(["media-001", " media-001 "])
