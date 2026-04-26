"""Action Class Contract model and deterministic loader utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from veritas_os.security.hash import canonical_json_dumps, sha256_of_canonical_json

SUPPORTED_CONTRACT_EXTENSIONS = {".yaml", ".yml", ".json"}
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "policies"
    / "action_contracts"
    / "schema.json"
)


class ActionClassContractValidationError(ValueError):
    """Raised when an Action Class Contract fails validation."""


@dataclass(frozen=True)
class ActionClassContract:
    """Machine-readable contract for regulated action governance.

    The contract defines whether an action class is admissible before crossing
    an execution boundary and captures fail-closed behavior requirements.
    """

    id: str
    version: str
    domain: str
    action_class: str
    description: str
    declared_intent: str
    allowed_scope: list[str]
    prohibited_scope: list[str]
    authority_sources: list[str]
    required_evidence: list[str]
    evidence_freshness: dict[str, Any]
    irreversibility: dict[str, Any]
    human_approval_rules: dict[str, Any]
    refusal_conditions: list[str]
    escalation_conditions: list[str]
    default_failure_mode: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping representation."""
        return {
            "id": self.id,
            "version": self.version,
            "domain": self.domain,
            "action_class": self.action_class,
            "description": self.description,
            "declared_intent": self.declared_intent,
            "allowed_scope": self.allowed_scope,
            "prohibited_scope": self.prohibited_scope,
            "authority_sources": self.authority_sources,
            "required_evidence": self.required_evidence,
            "evidence_freshness": self.evidence_freshness,
            "irreversibility": self.irreversibility,
            "human_approval_rules": self.human_approval_rules,
            "refusal_conditions": self.refusal_conditions,
            "escalation_conditions": self.escalation_conditions,
            "default_failure_mode": self.default_failure_mode,
            "metadata": self.metadata,
        }

    def deterministic_serialization(self) -> str:
        """Serialize contract into deterministic canonical JSON."""
        return canonical_json_dumps(self.to_dict())

    def deterministic_digest(self) -> str:
        """Compute deterministic SHA-256 digest from canonical JSON payload."""
        return sha256_of_canonical_json(self.to_dict())


def _normalize_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ActionClassContractValidationError(
            f"contract field '{field_name}' must be a string"
        )
    normalized = value.strip()
    if not normalized:
        raise ActionClassContractValidationError(
            f"contract field '{field_name}' must be non-empty"
        )
    return normalized


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ActionClassContractValidationError(
            f"contract field '{field_name}' must be an array of strings"
        )

    normalized_values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ActionClassContractValidationError(
                f"contract field '{field_name}' must contain only strings"
            )
        normalized_item = item.strip()
        if normalized_item:
            normalized_values.append(normalized_item)

    return normalized_values


def _ensure_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ActionClassContractValidationError(
            f"contract field '{field_name}' must be an object"
        )
    return dict(value)


def _validate_unknown_critical_fields(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if isinstance(key, str) and key.startswith("critical_"):
                raise ActionClassContractValidationError(
                    f"unknown critical field is not allowed: {path}.{key}"
                )
            _validate_unknown_critical_fields(nested_value, f"{path}.{key}")
    elif isinstance(value, list):
        for idx, nested_value in enumerate(value):
            _validate_unknown_critical_fields(nested_value, f"{path}[{idx}]")


def _validate_against_schema(
    data: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    required_fields = schema.get("required", [])
    properties = schema.get("properties", {})
    additional_properties = schema.get("additionalProperties", True)

    for field_name in required_fields:
        if field_name not in data:
            raise ActionClassContractValidationError(
                f"contract missing required field '{field_name}'"
            )

    if not additional_properties:
        unknown_keys = sorted(set(data.keys()) - set(properties.keys()))
        if unknown_keys:
            raise ActionClassContractValidationError(
                f"contract contains unknown fields: {', '.join(unknown_keys)}"
            )

    type_map = {
        "string": str,
        "array": list,
        "object": dict,
    }
    for field_name, rules in properties.items():
        if field_name not in data:
            continue
        expected_type = rules.get("type")
        if expected_type in type_map and not isinstance(
            data[field_name], type_map[expected_type]
        ):
            raise ActionClassContractValidationError(
                f"contract field '{field_name}' must be of type '{expected_type}'"
            )

    default_modes = properties.get("default_failure_mode", {}).get("enum", [])
    if data.get("default_failure_mode") not in default_modes:
        raise ActionClassContractValidationError(
            "contract field 'default_failure_mode' must be one of: "
            f"{', '.join(default_modes)}"
        )

    if "irreversibility" not in data:
        raise ActionClassContractValidationError(
            "contract field 'irreversibility' is required"
        )

    metadata = data.get("metadata", {})
    is_regulated = False
    if isinstance(metadata, dict):
        is_regulated = bool(metadata.get("regulated", False))
    if is_regulated:
        if not data.get("allowed_scope"):
            raise ActionClassContractValidationError(
                "regulated contract requires non-empty 'allowed_scope'"
            )
        if not data.get("prohibited_scope"):
            raise ActionClassContractValidationError(
                "regulated contract requires non-empty 'prohibited_scope'"
            )


def validate_action_class_contract(data: Mapping[str, Any]) -> ActionClassContract:
    """Validate raw mapping and return a typed ActionClassContract."""
    if not isinstance(data, Mapping):
        raise ActionClassContractValidationError(
            f"contract payload must be an object, got {type(data).__name__}"
        )

    _validate_unknown_critical_fields(data)
    schema = load_action_contract_schema(SCHEMA_PATH)
    _validate_against_schema(data, schema)

    normalized = {
        "id": _normalize_string(data["id"], "id"),
        "version": _normalize_string(data["version"], "version"),
        "domain": _normalize_string(data["domain"], "domain"),
        "action_class": _normalize_string(data["action_class"], "action_class"),
        "description": _normalize_string(data["description"], "description"),
        "declared_intent": _normalize_string(
            data["declared_intent"], "declared_intent"
        ),
        "allowed_scope": _normalize_string_list(data["allowed_scope"], "allowed_scope"),
        "prohibited_scope": _normalize_string_list(
            data["prohibited_scope"], "prohibited_scope"
        ),
        "authority_sources": _normalize_string_list(
            data["authority_sources"], "authority_sources"
        ),
        "required_evidence": _normalize_string_list(
            data["required_evidence"], "required_evidence"
        ),
        "evidence_freshness": _ensure_mapping(
            data["evidence_freshness"], "evidence_freshness"
        ),
        "irreversibility": _ensure_mapping(data["irreversibility"], "irreversibility"),
        "human_approval_rules": _ensure_mapping(
            data["human_approval_rules"], "human_approval_rules"
        ),
        "refusal_conditions": _normalize_string_list(
            data["refusal_conditions"], "refusal_conditions"
        ),
        "escalation_conditions": _normalize_string_list(
            data["escalation_conditions"], "escalation_conditions"
        ),
        "default_failure_mode": _normalize_string(
            data["default_failure_mode"], "default_failure_mode"
        ),
        "metadata": _ensure_mapping(data["metadata"], "metadata"),
    }

    return ActionClassContract(**normalized)


def load_action_contract_schema(path: str | Path) -> dict[str, Any]:
    """Load JSON schema used by Action Class Contract validation."""
    schema_path = Path(path)
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ActionClassContractValidationError(
            f"contract schema not found: {schema_path}"
        ) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActionClassContractValidationError(
            f"failed to load contract schema {schema_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ActionClassContractValidationError(
            "contract schema must decode to an object"
        )
    return payload


def load_action_class_contract(path: str | Path) -> ActionClassContract:
    """Load an Action Class Contract from YAML/JSON path."""
    contract_path = Path(path)
    suffix = contract_path.suffix.lower()
    if suffix not in SUPPORTED_CONTRACT_EXTENSIONS:
        raise ActionClassContractValidationError(
            f"unsupported contract file extension '{contract_path.suffix}'"
        )

    try:
        raw = contract_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ActionClassContractValidationError(
            f"contract file not found: {contract_path}"
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ActionClassContractValidationError(
            f"failed to read contract file {contract_path}: {exc}"
        ) from exc

    if not raw.strip():
        raise ActionClassContractValidationError(
            f"contract file is empty: {contract_path}"
        )

    try:
        loaded = (
            yaml.safe_load(raw)
            if suffix in {".yaml", ".yml"}
            else json.loads(raw)
        )
    except yaml.YAMLError as exc:
        raise ActionClassContractValidationError(
            f"invalid YAML in contract file {contract_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ActionClassContractValidationError(
            f"invalid JSON in contract file {contract_path}: {exc}"
        ) from exc

    return validate_action_class_contract(loaded)
