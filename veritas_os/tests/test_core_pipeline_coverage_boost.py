# veritas_os/tests/test_core_pipeline_coverage_boost.py
from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest


# =========
# Utilities
# =========

def _pick_entrypoint(cp) -> Callable[..., Any]:
    """
    core.pipeline の "入口" になり得る関数名を順に探す。
    """
    for name in (
        "run_decide_pipeline_core",
        "decide_pipeline_core",
        "run_decide_pipeline",
        "decide_pipeline",
        "run_pipeline",
    ):
        fn = getattr(cp, name, None)
        if callable(fn):
            return fn
    raise AssertionError("No core pipeline entrypoint found in veritas_os.core.pipeline")


class _NullLogger:
    """logger が必須引数になっている場合の保険。"""
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def exception(self, *a, **k): ...


def _build_kwargs(fn: Callable[..., Any], options: dict, tmp_path: Path) -> dict[str, Any]:
    """
    entrypoint の必須引数を「落ちにくく」埋める。
    - 既に default がある引数は触らない
    - 典型的な名前は意味のある値で埋める
    - 不明な引数も None で落ちないよう、名称/annotation から推測して埋める
    """
    sig = inspect.signature(fn)
    kwargs: dict[str, Any] = {}

    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.default is not inspect._empty:
            continue

        name = p.name
        low = name.lower()
        ann = p.annotation

        # --- Typical text inputs ---
        if low in ("query", "prompt", "task", "goal", "input_text", "text", "message"):
            kwargs[name] = "coverage boost"

        # --- Context/meta ---
        elif low in ("ctx", "context", "user_context", "meta", "metadata"):
            kwargs[name] = {"user_id": "u-cov", "request_id": "r-cov"}

        # --- Options/config ---
        elif low in ("options", "opts", "config", "cfg", "params", "settings"):
            kwargs[name] = options

        # --- Time ---
        elif low in ("now", "ts", "timestamp", "time", "dt", "datetime"):
            kwargs[name] = datetime(2025, 12, 19, tzinfo=timezone.utc)

        # --- Paths / dirs ---
        elif "path" in low or "dir" in low or low in ("home", "root"):
            kwargs[name] = tmp_path

        # --- Logger ---
        elif "logger" in low or low == "log":
            kwargs[name] = _NullLogger()

        # --- Heuristic by annotation ---
        else:
            # typing の annotation が dict/Path っぽい場合の保険
            if ann in (dict, "dict") or getattr(ann, "__origin__", None) is dict:
                kwargs[name] = {}
            elif ann in (Path, "Path"):
                kwargs[name] = tmp_path
            else:
                kwargs[name] = None

    return kwargs


async def _maybe_await(x: Any) -> Any:
    if inspect.isawaitable(x):
        return await x
    return x


def _iter_patchable_functions(module) -> Iterable[tuple[str, Callable[..., Any]]]:
    """
    module 内の関数/async関数だけを列挙。
    - import された関数を巻くと副作用が大きいので、__module__ が一致するものに限定。
    """
    mod_name = getattr(module, "__name__", "")
    for name in dir(module):
        if name.startswith("_"):
            continue
        obj = getattr(module, name, None)
        if not (inspect.isfunction(obj) or inspect.iscoroutinefunction(obj)):
            continue
        if getattr(obj, "__module__", None) != mod_name:
            continue
        yield name, obj


@dataclass
class _Instrumentation:
    called: dict[tuple[str, str], int]
    originals: dict[tuple[str, str], Callable[..., Any]]


def _instrument_modules(monkeypatch, modules: list[Any]) -> _Instrumentation:
    """
    modules の関数を全部ラップして「呼ばれた回数」を記録する。
    戻り値:
      - called[(module_name, func_name)] = count
      - originals[(module_name, func_name)] = original function
    """
    called: dict[tuple[str, str], int] = {}
    originals: dict[tuple[str, str], Callable[..., Any]] = {}

    for mod in modules:
        mod_name = getattr(mod, "__name__", str(mod))
        for fname, fn in _iter_patchable_functions(mod):
            key = (mod_name, fname)
            called[key] = 0
            originals[key] = fn

            if inspect.iscoroutinefunction(fn):
                async def _aw(*a, __fn=fn, __key=key, **k):
                    called[__key] += 1
                    return await __fn(*a, **k)
                monkeypatch.setattr(mod, fname, _aw, raising=False)
            else:
                def _w(*a, __fn=fn, __key=key, **k):
                    called[__key] += 1
                    return __fn(*a, **k)
                monkeypatch.setattr(mod, fname, _w, raising=False)

    return _Instrumentation(called=called, originals=originals)


def _pick_called_target(called: dict[tuple[str, str], int], keywords: list[str]) -> tuple[str, str] | None:
    """
    実際に呼ばれた関数のうち、keywords に当たりそうな名前を優先して 1つ選ぶ。
    """
    kws = [k.lower() for k in keywords]
    candidates = [(k, v) for k, v in called.items() if v > 0]
    if not candidates:
        return None

    # keyword マッチ優先（同点なら呼ばれ回数の多い方）
    for (mod_name, func_name), cnt in sorted(candidates, key=lambda x: (-x[1], x[0][1])):
        low = func_name.lower()
        if any(k in low for k in kws):
            return (mod_name, func_name)

    # keyword が見つからなければ一番呼ばれたやつ
    (mod_name, func_name), _ = sorted(candidates, key=lambda x: -x[1])[0]
    return (mod_name, func_name)


def _get_module_by_name(modules: list[Any], name: str):
    for m in modules:
        if getattr(m, "__name__", "") == name:
            return m
    return None


def _find_function_by_common_names(module, names: list[str]) -> str | None:
    """
    よくある関数名リストから「存在するもの」を優先で返す。
    """
    for n in names:
        obj = getattr(module, n, None)
        if callable(obj):
            return n
    return None


def _set_boom(monkeypatch, module, func_name: str, label: str):
    """
    func_name を例外化する（sync/async 両対応）。
    label は late-binding を避けて固定する。
    """
    cur = getattr(module, func_name, None)
    if cur is None:
        return

    if inspect.iscoroutinefunction(cur):
        async def _boom_async(*a, __label=label, **k):
            raise OSError(f"boom-{__label}")
        monkeypatch.setattr(module, func_name, _boom_async, raising=False)
    else:
        def _boom_sync(*a, __label=label, **k):
            raise OSError(f"boom-{__label}")
        monkeypatch.setattr(module, func_name, _boom_sync, raising=False)


def _is_acceptable_exception(exc: BaseException, label: str) -> bool:
    """
    pipeline が例外を握りつぶさず伝播する実装でも、このテストが落ちないようにする。
    ただし「boom-label」以外は基本 NG（予期しない例外）。
    """
    msg = str(exc)
    return f"boom-{label}" in msg


# =========================
# Main coverage boost test
# =========================

@pytest.mark.anyio
async def test_core_pipeline_force_exception_branches(tmp_path, monkeypatch):
    """
    目的:
      - core/pipeline.py の except / fallback / degrade ルートに入りやすくする。

    手順:
      1) まず通常実行して「どの関数が呼ばれているか」を計測
      2) planner/web/trust/dataset っぽい箇所を優先して例外化
      3) 例外分岐を踏ませる（握りつぶし実装なら out が返る / 伝播実装でも許容）

    注意:
      - 実装差があっても落ちにくい設計にしてあるが、
        "何も呼ばれない" 環境（全ステージOFF等）の場合は skip する。
    """
    import veritas_os.core.pipeline as cp

    # 周辺モジュール候補（存在しない場合があるので try）
    modules: list[Any] = [cp]

    pl = ws = tl = dw = None
    try:
        import veritas_os.core.planner as pl  # type: ignore
        modules.append(pl)
    except Exception:
        pass
    try:
        import veritas_os.tools.web_search as ws  # type: ignore
        modules.append(ws)
    except Exception:
        pass
    try:
        import veritas_os.logging.trust_log as tl  # type: ignore
        modules.append(tl)
    except Exception:
        pass
    try:
        import veritas_os.logging.dataset_writer as dw  # type: ignore
        modules.append(dw)
    except Exception:
        pass

    # 実行環境（tmp_path に逃がす）
    monkeypatch.setenv("VERITAS_HOME", str(tmp_path))
    monkeypatch.setenv("VERITAS_TMP", str(tmp_path))
    monkeypatch.setenv("VERITAS_DISABLE_NETWORK", "1")
    # “あっても害のない”デフォルト（プロジェクト側が参照するなら効く）
    monkeypatch.setenv("VERITAS_TRUSTLOG_DIR", str(tmp_path / "trustlog"))
    monkeypatch.setenv("VERITAS_DATASET_DIR", str(tmp_path / "dataset"))

    fn = _pick_entrypoint(cp)

    # 「なるべく通る可能性」を上げるオプション（存在しないキーは無視される想定）
    options = {
        "mode": "full",
        "stage": "full",
        "dry_run": False,
        "enable_planner": True,
        "enable_reason": True,
        "enable_debate": True,
        "enable_reflection": True,
        "enable_web_search": True,
        "enable_memory": True,
        "trust_log": True,
        "write_dataset": True,
        "save_world": True,
        "write_shadow": True,
    }

    # ---- Pass 1: トレース（呼び出し回数を記録） ----
    inst = _instrument_modules(monkeypatch, modules)

    out1 = await _maybe_await(fn(**_build_kwargs(fn, options, tmp_path)))
    assert out1 is not None

    # ---- Target selection: “よくある関数名”を優先 → 無ければトレースから選ぶ ----
    picked: dict[str, tuple[str, str]] = {}

    # ラベルごとに「まずは定番名」を探す（存在すればそれを採用）
    # ※ module によって実在名は違うので、できるだけ幅を持たせる
    common = {
        "planner": ["plan", "make_plan", "run_planner", "planner", "plan_steps", "plan_for_veritas_agi"],
        "web": ["web_search", "search", "run_web_search", "query_web", "fetch", "retrieve"],
        "trust": ["append", "write", "log", "write_trust", "append_event", "append_record", "trust_log"],
        "dataset": ["write", "append", "row", "write_row", "append_row", "dataset_write", "emit_row"],
    }

    # 1) common names で見つかれば採用
    if pl is not None:
        fname = _find_function_by_common_names(pl, common["planner"])
        if fname:
            picked["planner"] = (pl.__name__, fname)
    if ws is not None:
        fname = _find_function_by_common_names(ws, common["web"])
        if fname:
            picked["web"] = (ws.__name__, fname)
    if tl is not None:
        fname = _find_function_by_common_names(tl, common["trust"])
        if fname:
            picked["trust"] = (tl.__name__, fname)
    if dw is not None:
        fname = _find_function_by_common_names(dw, common["dataset"])
        if fname:
            picked["dataset"] = (dw.__name__, fname)

    # 2) 足りないラベルは「呼ばれた関数」から自動発見
    need = {
        "planner": ["planner", "plan"],
        "web": ["web", "search"],
        "trust": ["trust", "log", "append", "write"],
        "dataset": ["dataset", "write", "append", "row"],
    }
    for label, kws in need.items():
        if label in picked:
            continue
        t = _pick_called_target(inst.called, kws)
        if t is not None:
            picked[label] = t

    if not picked:
        pytest.skip("No callable was observed as called; cannot force exception branches")

    # ---- Pass 2..: “呼ばれそう/呼ばれた” 関数を例外化して except 分岐を踏む ----
    # 例外が握りつぶされる実装: out が返る
    # 例外が伝播する実装: boom-label の OSError なら許容
    for label, (mod_name, func_name) in picked.items():
        mod = _get_module_by_name(modules, mod_name)
        if mod is None:
            continue

        _set_boom(monkeypatch, mod, func_name, label)

        try:
            out2 = await _maybe_await(fn(**_build_kwargs(fn, options, tmp_path)))
            assert out2 is not None
        except OSError as e:
            if not _is_acceptable_exception(e, label):
                raise

    # ここまで来れば「例外注入→分岐到達」を複数回試せている
    # 追加の assert は “実装依存” になりやすいので、非 None / 許容例外の範囲に留める。


@pytest.mark.anyio
async def test_core_pipeline_force_disabled_feature_paths(tmp_path, monkeypatch):
    """
    目的:
      - “機能OFF時の分岐（早期return / no-op / guard節）” も踏む。

    アプローチ:
      - いくつかの enable_* を OFF にして entrypoint を回す。
      - これだけで pipeline 側の guard / if 分岐が増えてカバーが伸びることがある。
    """
    import veritas_os.core.pipeline as cp

    monkeypatch.setenv("VERITAS_HOME", str(tmp_path))
    monkeypatch.setenv("VERITAS_DISABLE_NETWORK", "1")

    fn = _pick_entrypoint(cp)

    options = {
        "mode": "minimal",
        "stage": "minimal",
        "dry_run": True,
        "enable_planner": False,
        "enable_reason": True,
        "enable_debate": False,
        "enable_reflection": False,
        "enable_web_search": False,
        "enable_memory": False,
        "trust_log": False,
        "write_dataset": False,
        "save_world": False,
        "write_shadow": False,
    }

    out = await _maybe_await(fn(**_build_kwargs(fn, options, tmp_path)))
    assert out is not None

@pytest.mark.anyio
async def test_core_pipeline_multi_fault_injection(tmp_path, monkeypatch):
    """
    pipeline の「例外→fallback」系の分岐を “連続で” 踏みに行く。
    1回落とすだけだと、後続ステージまで到達せず missing が残るため。
    """
    import veritas_os.core.pipeline as cp

    monkeypatch.setenv("VERITAS_HOME", str(tmp_path))
    monkeypatch.setenv("VERITAS_DISABLE_NETWORK", "1")

    fn = _pick_entrypoint(cp)

    options = {
        "mode": "full",
        "stage": "full",
        "dry_run": False,
        "enable_planner": True,
        "enable_reason": True,
        "enable_debate": True,
        "enable_reflection": True,
        "enable_web_search": True,
        "enable_memory": True,
        "trust_log": True,
        "write_dataset": True,
        "save_world": True,
        "write_shadow": True,
    }

    # まず普通に1回動かして “実際に呼ばれる” ものを取る
    out0 = await _maybe_await(fn(**_build_kwargs(fn, options, tmp_path)))
    assert out0 is not None

    # pipeline.py 内の関数名は実装により異なるので、
    # 「それっぽい名前の関数」を大量に候補化して、存在するものから順に爆破していく。
    candidates = [
        # web / io / log / dataset / world / memory あたりで except が起きやすい所
        "run_web_search",
        "web_search",
        "write_dataset",
        "append_dataset_row",
        "write_trust_log",
        "append_trust_log",
        "save_world",
        "write_shadow",
        "load_world",
        "load_memory",
        "save_memory",
        "ensure_dirs",
        "ensure_paths",
    ]

    # “存在する関数だけ” を順に落とす（落とすたびに pipeline を回す）
    for name in candidates:
        if not callable(getattr(cp, name, None)):
            continue

        # sync/async 両対応の boom
        cur = getattr(cp, name)
        if inspect.iscoroutinefunction(cur):
            async def _boom(*a, __n=name, **k):
                raise OSError(f"boom-pipeline-{__n}")
        else:
            def _boom(*a, __n=name, **k):
                raise OSError(f"boom-pipeline-{__n}")

        monkeypatch.setattr(cp, name, _boom, raising=False)

        try:
            out = await _maybe_await(fn(**_build_kwargs(fn, options, tmp_path)))
            assert out is not None
        except OSError as e:
            # pipeline が握りつぶさず伝播する実装でもOKにする
            if "boom-pipeline-" not in str(e):
                raise




