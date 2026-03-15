"""JSON parsing and extraction for Planner payloads.

This module centralizes the robust JSON extraction logic used by
``veritas_os.core.planner`` to recover structured plan data from
potentially malformed or noisy LLM output.

Extracted from ``planner.py`` to reduce file size and improve testability.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# LLMの暴走出力によるJSON救出時の過剰CPU使用を抑えるための上限
_MAX_JSON_EXTRACT_CHARS = 200_000
_MAX_JSON_DECODE_ATTEMPTS = 512
_MAX_STEPS_OBJECT_EXTRACT_ATTEMPTS = 512
_MAX_FENCED_BLOCK_SCAN_ATTEMPTS = 128

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _truncate_json_extract_input(raw: Any) -> str:
    """Normalize and size-limit JSON extraction input.

    The helper accepts arbitrary values because several planner call paths may
    pass non-string payloads during fallback handling. It also removes a UTF-8
    BOM and NUL bytes which frequently appear in streamed model output and can
    break JSON parsing.
    """
    if raw is None:
        return ""

    if not isinstance(raw, str):
        raw = str(raw)

    cleaned = raw.strip()
    if cleaned.startswith("\ufeff"):
        cleaned = cleaned.lstrip("\ufeff")
        logger.warning("planner JSON extraction removed leading BOM")

    if "\x00" in cleaned:
        cleaned = "".join(cleaned.split("\x00"))
        logger.warning("planner JSON extraction removed NUL bytes")

    if len(cleaned) <= _MAX_JSON_EXTRACT_CHARS:
        return cleaned

    logger.warning(
        "planner JSON extraction input too large (%d chars); truncating to %d chars",
        len(cleaned),
        _MAX_JSON_EXTRACT_CHARS,
    )
    return cleaned[:_MAX_JSON_EXTRACT_CHARS]


def _safe_json_extract_core(raw: str) -> Dict[str, Any]:
    """
    LLM の出力から JSON を安全に取り出す（救出エンジン）。
    ※ _safe_parse が外側の互換層。
    大きすぎる入力は先頭のみを使って解析し、DoSリスクを低減する。
    """
    if not raw:
        return {"steps": []}

    cleaned = _truncate_json_extract_input(raw)

    # ``` の先頭/末尾だけ来た時も対策
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    def _wrap_if_needed(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, list):
            return {"steps": obj}
        if isinstance(obj, dict):
            if isinstance(obj.get("steps"), list):
                return obj
            # stepsが無い/壊れてる場合も必ず安定化
            obj.setdefault("steps", [])
            if isinstance(obj.get("steps"), dict):
                obj["steps"] = [obj["steps"]]
            elif not isinstance(obj.get("steps"), list):
                obj["steps"] = []
            return obj
        return {"steps": []}

    def _iter_decoded_json_values(text: str):
        """Yield JSON values decoded from free-form text.

        The probe count is bounded to avoid excessive CPU usage when malformed
        text contains a very large number of ``{"`` / ``[`` characters.
        Candidates that cannot possibly close are skipped before decoding
        attempts.
        """
        decoder = json.JSONDecoder()
        attempts = 0
        last_obj_close = text.rfind("}")
        last_list_close = text.rfind("]")

        for i, ch in enumerate(text):
            if ch not in "[{":
                continue

            if attempts >= _MAX_JSON_DECODE_ATTEMPTS:
                logger.warning(
                    "planner JSON decoder probe limit reached (%d attempts)",
                    _MAX_JSON_DECODE_ATTEMPTS,
                )
                return None

            attempts += 1

            if ch == "{" and i > last_obj_close:
                continue
            if ch == "[" and i > last_list_close:
                continue

            try:
                obj, _ = decoder.raw_decode(text, idx=i)
                yield obj
            except json.JSONDecodeError:
                continue

    # 1) そのまま
    try:
        obj = json.loads(cleaned)
        return _wrap_if_needed(obj)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.debug("planner JSON parse attempt 1 (raw) failed")

    # 1.5) 先頭ノイズ付きの JSON を raw_decode で救済
    fallback_from_raw_decode: Optional[Dict[str, Any]] = None
    for obj in _iter_decoded_json_values(cleaned):
        if isinstance(obj, list):
            return _wrap_if_needed(obj)

        if isinstance(obj, dict) and "steps" in obj:
            return _wrap_if_needed(obj)

        if isinstance(obj, dict) and fallback_from_raw_decode is None:
            fallback_from_raw_decode = _wrap_if_needed(obj)

    if fallback_from_raw_decode and cleaned.lstrip().startswith("{"):
        return fallback_from_raw_decode

    # 2) {} 抜き出し（旧来互換の救済）
    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        snippet = cleaned[start:end]
        obj = json.loads(snippet)
        return _wrap_if_needed(obj)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.debug("planner JSON parse attempt 2 (brace extraction) failed")

    # 3) 末尾削り
    max_len = len(cleaned)
    attempts = 0
    max_attempts = 500

    for cut in range(max_len, 1, -1):
        if attempts >= max_attempts:
            break
        ch = cleaned[cut - 1]
        if ch not in ("}", "]"):
            continue
        attempts += 1
        candidate = cleaned[:cut]
        try:
            obj = json.loads(candidate)
            return _wrap_if_needed(obj)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

    # 4) "steps":[{...},{...}] から dict だけ拾う（最後の保険）
    #    NOTE: 以前の手書きパーサよりも、JSONDecoder を使って保守性を向上。
    def _extract_step_objects(text: str) -> List[Dict[str, Any]]:
        """Extract dict objects from a ``"steps"`` JSON-like array.

        This parser is intentionally tolerant to partially broken LLM output.
        It scans forward from ``"steps": [`` and decodes each object candidate
        with ``json.JSONDecoder().raw_decode``. The decode attempt count is
        bounded to reduce CPU abuse risk from malformed inputs.
        """
        idx = text.find('"steps"')
        if idx == -1:
            return []
        idx = text.find("[", idx)
        if idx == -1:
            return []

        objs: List[Dict[str, Any]] = []
        decoder = json.JSONDecoder()
        attempts = 0
        i = idx + 1
        n = len(text)

        while i < n:
            if attempts >= _MAX_STEPS_OBJECT_EXTRACT_ATTEMPTS:
                logger.warning(
                    "planner step object extraction attempt limit reached (%d)",
                    _MAX_STEPS_OBJECT_EXTRACT_ATTEMPTS,
                )
                break

            ch = text[i]
            if ch == "]":
                break

            if ch != "{":
                i += 1
                continue

            attempts += 1
            try:
                obj, end = decoder.raw_decode(text, idx=i)
            except json.JSONDecodeError:
                i += 1
                continue

            if isinstance(obj, dict):
                objs.append(obj)
            i = end

        return objs

    step_objs = _extract_step_objects(cleaned)
    if step_objs:
        return {"steps": step_objs}

    return {"steps": []}


def _safe_parse(raw: Any) -> Dict[str, Any]:
    """
    テスト互換用（debate と同系）。
    - dict -> dict
    - list -> {"steps": list}
    - str  -> fenced除去 + JSON救出
    - その他 -> str化して救出
    戻りは必ず {"steps": [...]} を含む dict。
    """
    if raw is None:
        return {"steps": []}

    if isinstance(raw, dict):
        d = dict(raw)
        # steps が list でなければ空に寄せる
        if not isinstance(d.get("steps"), list):
            if isinstance(d.get("steps"), dict):
                d["steps"] = [d["steps"]]  # 変なモデル出力救済
            else:
                d.setdefault("steps", [])
        return d

    if isinstance(raw, list):
        return {"steps": raw}

    if not isinstance(raw, str):
        raw = str(raw)

    s = _truncate_json_extract_input(raw)
    if not s:
        return {"steps": []}

    fallback_parsed: Optional[Dict[str, Any]] = None
    fenced_attempts = 0
    for fence_match in _FENCE_RE.finditer(s):
        if fenced_attempts >= _MAX_FENCED_BLOCK_SCAN_ATTEMPTS:
            logger.warning(
                "planner fenced JSON scan limit reached (%d blocks)",
                _MAX_FENCED_BLOCK_SCAN_ATTEMPTS,
            )
            break

        fenced_attempts += 1
        fenced = fence_match.group(1).strip()
        parsed = _safe_json_extract_core(fenced)
        if parsed.get("steps"):
            return parsed
        if fallback_parsed is None:
            fallback_parsed = parsed

    if fallback_parsed is not None:
        return fallback_parsed

    return _safe_json_extract_core(s)


def _safe_json_extract(raw: str) -> Dict[str, Any]:
    """
    互換のため残す（既存コード/テストが参照する可能性）。
    実体は _safe_parse → _safe_json_extract_core。
    """
    return _safe_parse(raw)
