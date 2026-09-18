from __future__ import annotations

from pathlib import Path

from veritas_os.scripts.cage_provider03_phase5b_runner import audit_cage_source


def _write_sources(
    root: Path,
    *,
    provider_handlers: str,
    kernel_handlers: str,
) -> None:
    provider_path = root / "src/integrations/provider_03/provider.py"
    kernel_path = root / "src/gateway/governance/normative_provider.py"
    provider_path.parent.mkdir(parents=True, exist_ok=True)
    kernel_path.parent.mkdir(parents=True, exist_ok=True)

    provider_path.write_text(
        f"""
class Provider03NormativeProvider:
    async def validate_fria(self, payload):
        try:
            return payload
{provider_handlers}
""".lstrip(),
        encoding="utf-8",
    )
    kernel_path.write_text(
        f"""
async def enforce_fria_boundary(provider, action_context):
    try:
        return await provider.validate_fria(action_context)
{kernel_handlers}
""".lstrip(),
        encoding="utf-8",
    )


def test_source_audit_detects_current_gap_shape(tmp_path: Path) -> None:
    _write_sources(
        tmp_path,
        provider_handlers=(
            "        except httpx.HTTPStatusError:\n"
            "            return None\n"
            "        except httpx.RequestError:\n"
            "            return None\n"
        ),
        kernel_handlers=(
            "    except asyncio.TimeoutError:\n"
            "        return None\n"
        ),
    )

    audit = audit_cage_source(tmp_path)

    assert audit["provider03_validate_catches_json_decode_error"] is False
    assert audit["provider03_validate_catches_generic_exception"] is False
    assert audit["provider03_validate_exception_handlers"] == [
        "httpx.HTTPStatusError",
        "httpx.RequestError",
    ]
    assert audit["sync_gate_validate_exception_handlers"] == ["asyncio.TimeoutError"]
    assert audit["sync_gate_catches_generic_exception"] is False


def test_source_audit_detects_closed_response_exception_boundary(tmp_path: Path) -> None:
    _write_sources(
        tmp_path,
        provider_handlers=(
            "        except (json.JSONDecodeError, ValueError):\n"
            "            return None\n"
            "        except httpx.RequestError:\n"
            "            return None\n"
            "        except Exception:\n"
            "            return None\n"
        ),
        kernel_handlers=(
            "    except asyncio.TimeoutError:\n"
            "        return None\n"
            "    except Exception:\n"
            "        return None\n"
        ),
    )

    audit = audit_cage_source(tmp_path)

    assert audit["provider03_validate_catches_json_decode_error"] is True
    assert audit["provider03_validate_catches_generic_exception"] is True
    assert audit["sync_gate_catches_generic_exception"] is True
