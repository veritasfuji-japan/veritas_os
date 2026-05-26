"""Local/offline controlled live V.I.K.I. synthetic ingestion endpoint skeleton.

This module models an endpoint-like request boundary as a pure local runtime
helper. It does not implement a network listener, HTTP server, routes, port
binding, credentials, replay cache, logging, telemetry, observability, or live
V.I.K.I. integration.
"""

from __future__ import annotations

from veritas_os.governance.controlled_live_viki_interface import (
    receive_controlled_live_viki_payload,
)

CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH = "/synthetic/controlled-live-viki"
CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD = "POST"
CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_CONTENT_TYPE = "application/json"

CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD_NOT_ALLOWED = (
    "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD_NOT_ALLOWED"
)
CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH_NOT_FOUND = (
    "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH_NOT_FOUND"
)
CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_UNSUPPORTED_MEDIA_TYPE = (
    "CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_UNSUPPORTED_MEDIA_TYPE"
)

_RESPONSE_SOURCE = "controlled_live_viki_synthetic_ingestion_endpoint"
_ENDPOINT_MODE = "local_synthetic_runtime_skeleton"
_DISABLED_REASON_CODE = "CONTROLLED_LIVE_DISABLED"


def _build_fail_closed_endpoint_response(
    *,
    endpoint_enabled: bool,
    http_status: int,
    receiver_result: dict[str, object] | None,
    reason_code: str,
    accepted_for_processing: bool,
) -> dict[str, object]:
    return {
        "endpoint_mode": _ENDPOINT_MODE,
        "endpoint_enabled": endpoint_enabled,
        "http_status": http_status,
        "accepted_for_processing": accepted_for_processing,
        "response_source": _RESPONSE_SOURCE,
        "receiver_result": receiver_result,
        "reason_code": reason_code,
        "final_commit_approved": False,
    }


def _reason_code(result: dict[str, object]) -> str:
    return str(result.get("reason_code") or result.get("veritas_reason_code") or "")


def handle_controlled_live_viki_synthetic_ingestion_request(
    payload: object,
    *,
    feature_flag_value: str | None,
    method: str = CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD,
    path: str = CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH,
    content_type: str = CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_CONTENT_TYPE,
) -> dict[str, object]:
    """Handle a local synthetic ingestion request in a fail-closed manner."""
    endpoint_enabled = feature_flag_value == "true"

    if method != CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD:
        return _build_fail_closed_endpoint_response(
            endpoint_enabled=endpoint_enabled,
            http_status=405,
            receiver_result=None,
            reason_code=CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_METHOD_NOT_ALLOWED,
            accepted_for_processing=False,
        )

    if path != CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH:
        return _build_fail_closed_endpoint_response(
            endpoint_enabled=endpoint_enabled,
            http_status=404,
            receiver_result=None,
            reason_code=CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_PATH_NOT_FOUND,
            accepted_for_processing=False,
        )

    if content_type != CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_CONTENT_TYPE:
        return _build_fail_closed_endpoint_response(
            endpoint_enabled=endpoint_enabled,
            http_status=415,
            receiver_result=None,
            reason_code=CONTROLLED_LIVE_SYNTHETIC_ENDPOINT_UNSUPPORTED_MEDIA_TYPE,
            accepted_for_processing=False,
        )

    receiver_result = receive_controlled_live_viki_payload(
        payload,
        feature_flag_value=feature_flag_value,
    )

    reason_code = _reason_code(receiver_result)

    if not endpoint_enabled:
        return _build_fail_closed_endpoint_response(
            endpoint_enabled=False,
            http_status=503,
            receiver_result=receiver_result,
            reason_code=_DISABLED_REASON_CODE,
            accepted_for_processing=False,
        )

    accepted_for_processing = reason_code.startswith("CONTROLLED_LIVE_RSA_HANDOFF_")
    http_status = 202 if accepted_for_processing else 422

    return _build_fail_closed_endpoint_response(
        endpoint_enabled=True,
        http_status=http_status,
        receiver_result=receiver_result,
        reason_code=reason_code,
        accepted_for_processing=accepted_for_processing,
    )
