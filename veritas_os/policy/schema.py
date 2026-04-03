"""Policy loader and strict validation entrypoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import ValidationError

from .models import PolicyValidationError, SourcePolicy


SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".json"}


def _load_source_file(path: Path) -> Dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise PolicyValidationError(
            f"unsupported policy file extension '{path.suffix}'"
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PolicyValidationError(f"policy file not found: {path}") from exc
    except UnicodeDecodeError as exc:
        raise PolicyValidationError(
            f"policy file is not valid UTF-8: {path}"
        ) from exc
    except OSError as exc:
        raise PolicyValidationError(
            f"failed to read policy file {path}: {exc}"
        ) from exc

    if not raw.strip():
        raise PolicyValidationError(f"policy file is empty: {path}")

    try:
        if suffix in {".yaml", ".yml"}:
            loaded = yaml.safe_load(raw)
        else:
            loaded = json.loads(raw)
    except yaml.YAMLError as exc:
        raise PolicyValidationError(
            f"invalid YAML in policy file {path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise PolicyValidationError(
            f"invalid JSON in policy file {path}: {exc}"
        ) from exc

    if not isinstance(loaded, dict):
        raise PolicyValidationError(
            f"policy source must decode to a mapping object, got {type(loaded).__name__}"
        )
    return loaded


def validate_source_policy(data: Dict[str, Any]) -> SourcePolicy:
    """Validate raw source policy mapping into strict typed model."""
    try:
        return SourcePolicy.model_validate(data)
    except ValidationError as exc:
        raise PolicyValidationError(f"invalid policy: {exc}") from exc


def load_and_validate_policy(path: str | Path) -> SourcePolicy:
    """Load a policy from YAML/JSON and validate against strict schema."""
    policy_path = Path(path)
    source = _load_source_file(policy_path)
    return validate_source_policy(source)
