# VIGIL Layer 1 — Source and Media Schema Specification

**Status:** Initial implementation specification  
**Scope:** Camera, MediaAsset, SourceReference and Artifact

## 1. Camera

**Python file:** `src/vigil/domain/camera.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `camera_id` | `str` | Yes | Stable unique identifier for the camera. |
| `name` | `str` | Yes | Human-readable camera name. |
| `location_label` | `str \| None` | No | Physical location of the camera, if known. |
| `timezone` | `str \| None` | No | IANA timezone associated with the camera, if known. |
| `clock_offset_seconds` | `float \| None` | No | Correction applied to the camera-reported clock to estimate reference time. |

**Validation rules**

- IDs and names must not be empty.
- Timezones must be valid IANA timezone names.
- Clock offsets must be finite numbers.
- Unknown metadata must remain explicitly optional.

## 2. MediaAsset

**Python file:** `src/vigil/domain/media_asset.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `media_asset_id` | `str` | Yes | Stable unique identifier for the original media. |
| `media_type` | `video \| audio \| image` | Yes | Type of original media. |
| `storage_uri` | `str` | Yes | Location or storage key for the original media. |
| `camera_id` | `str \| None` | No | Identifier of the producing camera, if known. |
| `duration_seconds` | `float \| None` | No | Positive duration in seconds, if applicable and known. |
| `recorded_at` | `datetime \| None` | No | Timezone-aware wall-clock time corresponding to the recording's beginning. |
| `sha256` | `str \| None` | No | SHA-256 checksum of the original media, when available. |

**Validation rules**

- IDs and storage references must not be empty.
- Media type must be one of the declared values.
- Duration must be positive and finite when supplied.
- Recording timestamps must be timezone-aware.
- SHA-256 checksums must contain exactly 64 hexadecimal characters.
- The referenced camera must exist when `camera_id` is supplied.

## 3. SourceReference

**Python file:** `src/vigil/domain/source_reference.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `media_asset_id` | `str` | Yes | Identifier of the original media containing the evidence. |
| `start_seconds` | `float` | Yes | Inclusive start position in seconds on the original media timeline. |
| `end_seconds` | `float` | Yes | Exclusive end position in seconds on the original media timeline. |
| `source_timestamp` | `datetime \| None` | No | Timezone-aware wall-clock timestamp corresponding to `start_seconds`, when known. |

**Validation rules**

- Media IDs must not be empty.
- Timeline positions must be finite and non-negative.
- `end_seconds` must be strictly greater than `start_seconds`.
- Wall-clock timestamps must be timezone-aware.
- When media duration is known, the interval must not extend beyond it.
- Source references must resolve to existing media assets.

## 4. Artifact

**Python file:** `src/vigil/domain/artifact.py`

| Attribute | Type | Required | Description |
|---|---|---|---|
| `artifact_id` | `str` | Yes | Stable unique identifier for the derived artifact. |
| `artifact_type` | `frame \| crop \| clip \| audio_segment \| derived_media` | Yes | Kind of derived media. |
| `media_type` | `video \| audio \| image` | Yes | Actual media type of the stored artifact. |
| `storage_uri` | `str` | Yes | Location of the derived media. |
| `source_reference` | `SourceReference` | Yes | Original media and timeline interval from which the artifact was derived. |
| `sha256` | `str \| None` | No | SHA-256 checksum of the derived artifact, when available. |
| `created_at` | `datetime` | Yes | Timezone-aware timestamp when the artifact was created; defaults to UTC now. |

**Validation rules**

- Artifact IDs and storage references must not be empty.
- `frame` and `crop` require image media.
- `clip` requires video media.
- `audio_segment` requires audio media.
- `derived_media` may represent any declared media type.
- Creation timestamps must be timezone-aware.
- Checksums must contain exactly 64 hexadecimal characters when supplied.
- Source references must resolve to existing media assets.
- The source interval must be valid for the referenced media.

## Shared conventions

- IDs are opaque, non-empty strings; their generation mechanism is not specified by these schemas.
- Media-relative times are expressed in seconds.
- Source intervals use the half-open convention `[start_seconds, end_seconds)`.
- Wall-clock timestamps must include timezone information.
- Unknown information is represented with optional fields, not fabricated defaults.
- Cross-record relationships must be checked by the repository or service layer.
- Schema changes must be accompanied by tests and documentation updates.
