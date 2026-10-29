# Control surface review — 2026-10-29

## Scope and disposition

Reviewed source: `cdfffc1681820dcf9c599f3725e7252fb4364f22` (main after #2435).
This is a **non-destructive first-pass inventory and review backlog**, not an
independent security certification or a completed whole-program effect audit.
No runtime, credential, policy, dependency, workflow or frozen-proof behavior is
changed. No permission to delete modules or activate an integration is granted.

The companion [source index](2026-10-29-control-surface-index.json) records every
match of the stated discovery rules, including read routes, prototypes and
scripts. It intentionally does not label every POST as a business effect or
every missing Bind marker as a vulnerability. Its entries are not an expanded
Bind allowlist. Counts describe this source pin only.

| Discovered at the pin | Count | Interpretation |
| --- | ---: | --- |
| Tracked Python files, whole repository | 1,332 | Includes scripts, test helpers and fixtures |
| Python files under `veritas_os/` | 1,014 | 550 under `veritas_os/tests/`; 464 elsewhere, not necessarily all production runtime |
| Python files under root `tests/` | 158 | A separate test tree; excluding it misses core tests |
| Literal route decorators in non-test Python | 60 | Declarations, not distinct mounted product endpoints |
| Additional route-registration calls | 1 | Optional Prometheus `/metrics`; separate from `/v1/metrics` |
| Next.js API route files | 6 | Includes the catch-all BFF and static routes |
| Python files with a main guard / shell files | 173 / 24 | Execution candidates; neither reachability nor effect classification is proven |
| `do_*` HTTP handler definitions / selected background calls | 8 / 11 | Non-FastAPI and background candidates retained for review |
| Workflow files | 53 | Event filters and declared job keys are in the index; not 53 required checks |

Discovery parses tracked Python without importing application modules and reads
workflow YAML with `BaseLoader`. It recognizes literal route decorators,
`add_api_route`/`add_route`/`mount`/`add_websocket_route`, main guards, HTTP handler
names and selected background-call names. It does not resolve aliases, arbitrary
reflection, plugin loading, arbitrary process launch, deployments or complete
transitive effects. Script inventory is not restricted to `scripts/`: e.g.
package scripts, root launchers and SDK examples can be execution candidates.
No-match is not proof of absence. Do not claim universal bypass closure from it.

## Existing inventories answer different questions

| Source | What was inspected | Boundary / disposition |
| --- | --- | --- |
| `veritas_os/policy/bind_coverage_registry.py` | Six declared operations: three exact BCBR runtime boundaries, SaaS demo, AML/KYC fixture, governance policy update | Not the complete API inventory. Metadata validation alone does not execute every negative case. |
| `veritas_os/api/bind_target_catalog.py` | Five operator-facing targets: policy update, bundle promotion, compliance configuration, halt, resume | UI/filter metadata, not runtime authorization or a replacement for the registry. |
| `scripts/quality/check_bind_coverage_bypass_resistance_v1.py` | Reviewed dependency/capability/sink inventories under `veritas_os/policy` | Bounded AST proof domain. Does not cover all API, core, tools, CLI, shell or auxiliary-service effects. |
| `scripts/audit_large_consolidation.py` | Existing file/import/symbol and candidate-family inventory | Reused; naming and size do not authorize deletion. Its test total covers only `veritas_os/tests/`, not root `tests/`. |
| `scripts/audit_large_consolidation_phase2.py` | Existing frozen dependency closure, role/consumer and duplicate-candidate matrices | Reused; a current run still emits historical `source_main=52752dbf766d9994f2f3267af47e904748d347a6`. Keep historical and newly executed source identities separate. |

The registry/catalog difference is an **inventory alignment task**, not evidence
that the other four catalog targets bypass Bind. The actual management handlers
call Bind helpers. Conversely, adding rows to a registry would not protect an
unprotected sink. A future cross-check must state its exact expected domain and
must not silently widen `BIND_COVERAGE_BYPASS_RESISTANCE_V1`.

## Runtime/control matrix from source review

`veritas_os/api/server.py` mounts decide/memory/trust/WAT routers with API-key and rate-limit
dependencies; governance adds its authenticated role/tenant guard; system and
observability use API-key authentication. SSE and WebSocket own their admission.
Endpoint permissions are additional to those inherited dependencies. These are
source observations, not proof that deployed network and credentials enforce
the same boundaries. The index retains declarations outside the main app too.

| Entry or family | Effect / observed controls | Evidence to start from | Still to establish |
| --- | --- | --- | --- |
| `POST /v1/decide` | Pipeline/provider and local persistence effects; `decide` permission, halt admission and configured signature controls; a decision is not external execution authority | `api/routes_decide.py`; `test_system_authenticated_actors.py`; frozen Decision-to-Effect proof | Trace every selected tool/persistence/maintenance branch, including configuration-dependent execution. |
| `POST /v1/replay/{decision_id}` | Writes an audit replay report; explicit signature check and `strict=True` | `api/routes_decide.py`; `test_replay_http_nonce_window.py`; replay tests | Complete transitive no-external-effect inventory; not a general network-isolation claim. |
| `POST /v1/decision/replay/{decision_id}` | Audit replay; `trust_log_read`, explicit refusal of mock disabling, passes `mock_external_apis=True` | `test_security_f06_f07_replay_trust_rbac.py` | Keep the two replay contracts distinct; inspect all persistence and provider branches. |
| `POST /v1/fuji/validate` | `decide` permission; validation output is not a consumed execution permit | `api/routes_decide.py`; FUJI tests | Trace configured validator side effects before classifying the entire call as pure. |
| `PUT /v1/governance/policy` | Authenticated actor, governance permission/tenant guard, four-eyes validation, current policy and Bind helper; reserved override rejected | `test_governance_policy_bind_path.py`; `integration/test_governance_api.py`; `test_governance_authenticated_scope.py` | Actual enterprise approver identity, filesystem/database ownership and concurrent change conditions. |
| `POST /v1/governance/policy-bundles/promote` | Authenticated actor, `governance_write`, current policy, Bind helper, reserved override rejection and adapter signature/content verification | `integration/test_governance_api.py`; promotion/verification tests | Independent signer custody; mutable filesystem race and deployment boundary. |
| `PUT /v1/compliance/config` | `config_write`, authenticated actor, current governance policy, Bind helper; local runtime configuration changes | `integration/test_governance_api.py`; `policy/compliance_config_update.py` | Signed human approval is not implied by a server-created approval boolean. Document exact policy-dependent evidence requirements. |
| `POST /v1/system/halt`, `/v1/system/resume` | `config_write`, authenticated actor and current policy via Bind helpers; process-local state | `test_system_halt_worker_boundary.py`; `test_halt_startup_restart.py`; system/API tests | Distributed halt and independent-host recovery are not provided by rejecting strict multi-worker configurations. |
| `POST /v1/memory/put`, `/v1/memory/erase` | `memory_write`, key-derived user resolution, owner metadata / backend erasure and legal-hold logic; no route Bind marker | `test_security_f04_f05_principal_memory_isolation.py`; `test_memory_compliance.py`; `scenario/test_memory_gdpr_erasure.py` | Review every backend/fallback and deletion attribution. Classify retention/deletion risk explicitly before deciding whether additional Bind/approval is required. |
| `POST /v1/memory/get`, `/v1/memory/search` | Read-style POSTs with `memory_read` and user resolution | Memory security/isolation and route tests | Ownership on every backend/fallback, incidental caches/logs; method alone is not an effect classification. |
| `POST /v1/trust/feedback` | `trust_feedback_write`, authenticated principal, ValueCore append and event; no route Bind marker | `test_security_f06_f07_replay_trust_rbac.py` | Shared BFF backend key remains a different identity from an end user; inspect downstream feedback consumers. |
| WAT issue/validate/revoke POSTs | `decide` permission; shadow audit events; confirmed revocation requires explicit phrase; not execution authority | `tests/test_wat_api.py`; `test_wat_events.py`; WAT verifier tests | Phrase is not independent authenticated approval. Review event ownership/provenance and retained-store replacement/rollback separately. |
| SSE `/v1/events`, WS `/v1/ws/trustlog` | Admission, current key/role event filtering, bounded slots/sends and cleanup; read delivery | `test_stream_authorization.py`; `test_stream_real_uvicorn.py`; `stream-real-uvicorn.yml` | Not durable delivery, enterprise IdP revocation, per-object/tenant isolation or independent-host proof. |
| Other GET routes in `api/routes_*.py` | Read/report/health/metrics surfaces with the declared router/route guards; public health/status intentionally separate | All declarations in source index; `veritas_os/api/server.py` mounts; endpoint tests | Read authorization, object visibility and incidental report/cache writes still require per-handler review. |
| `api/dashboard_server.py` | Separate FastAPI app; dashboard/status/report download use HTTP Basic; health separate | Dashboard implementation/tests | Not automatically protected by main API startup/RBAC. Review deployed exposure and local report/credential storage. |
| CAGE Phase5A runtime | Separate Bearer-protected fixture service, deterministic governance projection and evidence-reference seal; no external-effect authority | `tests/governance/test_cage_provider03_phase5a_runtime.py` | Preserve prototype scope; neither its seal nor APPROVED projection is a production execution permit. |
| Sandbox event service / IAM lab target | Separate effect receivers; sandbox writer/reader tokens; IAM mTLS/Permit/source checks and target ledger | Controlled composition, native IAM Docker/PostgreSQL workflows; `scripts/enterprise_iam_lab/target_service.py` | Same-host synthetic tests do not prove independent operators, customer IAM or cross-host nonce consensus. |
| `core/tools.py`, `tools/*`, pipeline execution | Tool allow/block lists, provenance/egress checks, configured search/LLM calls | `test_core_tools.py`; `test_tools.py`; `test_tools_env.py`; `core/pipeline_execute.py` | An allowlist is not the frozen native single-use boundary. Map every reachable implementation and credential before adding write tools. |
| Packaged CLIs | `veritas-migrate`, `veritas-trustlog-verify`, `veritas-evidence-bundle`; local OS/DB/file authority | `pyproject.toml`; `veritas_os/cli/*` tests | HTTP RBAC is not a CLI boundary. Review command options, file writes, DB roles and destructive operations under OS controls. |
| Operational scripts / background candidates | Backup/restore/drill, health/alert helpers, maintenance, API cleanup schedulers; complete heuristic candidate lists in index | `api/lifespan.py`; auth/rate cleanup; `scripts/restore_postgres.sh`; package scripts | Do not execute to audit. Review OS credentials, actual launcher/configuration, retry behavior and allowed mutations individually. |

Tests named without a directory prefix above are under `veritas_os/tests/` unless
otherwise stated. They are starting evidence, not a claim that every listed suite
was rerun in this review. Individual object authorization and full call-graph
effect classification remain open; the discovery pass does not close them.

## Core decision test review

`tests/governance/test_commit_boundary.py` directly exercises the evaluator with
16 tests: commit, missing/invalid contract, missing/expired/indeterminate
authority, prohibited scopes, missing/stale evidence, approval requirements,
undefined boundary, validator error handling, deterministic result and order.
Other authority-ingestion and Bind-receipt tests also reference the component.
`pyproject.toml` and the normal CI shard selector both include root `tests/`.
The existing file disproves an absence-of-unit-tests claim, not a claim of
complete branch coverage.

`_resolve_outcome` handles `escalate`, `refuse`, `block`, then checks intent
admissibility before returning `commit`. It is not an unconditional default-deny
switch. The built-in validator constructs a constrained outcome; the evaluator
also accepts an injected validator. The direct suite always supplies the same
admissible intent and does not directly enumerate malformed recommendations,
all intent shapes, contradictory result/predicate combinations or the exact
metadata merge precedence. These are **test/review gaps**, not a demonstrated
HTTP exploit or permission to alter outcome semantics.

Next bounded kernel work should write a decision table, locate any coverage in
other suites, then test valid commit controls, all deny outcomes, invalid/missing
recommendations, intent mismatches, false/non-boolean flags, stale+failed/missing
combinations, and exception boundaries. Determine supported validator contracts
before proposing a change. Preserve the distinction between escalation and
execution permission; no new permissive fallback is authorized.

## Module and CI consolidation disposition

| Family | Role / disposition | Condition before any consolidation |
| --- | --- | --- |
| `neomundi_rgc_v01_complete*`, `neomundi_rgc_v02*` | KEEP version-specific signature/measurement acceptance; both feed the existing provider-neutral external-measurement boundary | Prove canonical bytes, version binding, complete/partial semantics, key provenance, freshness and replay rejection unchanged. A generic boundary already exists in `veritas_os/governance/external_measurement_evidence.py`. |
| `cage_provider03_phase3*`, `phase5*` | KEEP fixture/prototype/runner distinctions while consumers remain | Inventory downstream contracts, fixture hashes, endpoint consumers and run evidence; filenames alone do not prove redundancy. |
| `controlled_live_viki_*` | UNCERTAIN integration/receiver/adapter boundaries; not removable by prefix | Follow the default-disabled and authority-separation tests and operational callers before any deletion. |
| Canonical/live adapter dry-run families | Frozen transitive dependencies and compatibility candidates, not disposable copies | Existing Phase2 current-checkout closure contains 136 runtime and 168 proof files with 11 suffix pairs; static-import limitation remains. |
| TrustLog verifier / CLI surfaces | Different encrypted/full/witness/public verification roles | Reuse the existing Phase2 role/consumer matrix. Do not merge different trust assumptions into a permissive verifier. |
| 53 workflow definitions | General CI, independent proof scopes, security/publication and manual/production lanes | The index records each event filter and job ID. Compare actual required jobs, artifact identities, dependencies and run timings before extracting common setup. No proof job or negative case is removed. |

Workflow starting points: `main.yml` (Python shards, PostgreSQL, frontend),
`bind-coverage-bypass-resistance-v1.yml` (frozen sink inventory),
`reproducible-decision-to-effect-e2e.yml` and
`reproducible-reconciliation-capable-execution-profile.yml` (controlled chain),
`auth-real-redis.yml`, `stream-real-uvicorn.yml`, `isolated-iam-*.yml`,
`veritas-cage-*.yml`, `observable-digest-resolver-aer*.yml`, plus security and
publication workflows. Their existence is not evidence that they ran on this
main SHA; exact-source CI results and artifact inspection are separate gates.

## Prioritized follow-up with acceptance criteria

| Priority / item | Evidence and risk | Bounded next deliverable / completion |
| --- | --- | --- |
| P0 — effect coverage outside the policy scanner | API/local persistence, tools, CLI, shell and service candidates are not all in the BCBR proof domain | Choose one destructive/state-changing entry, starting with memory erase or an operational restore path; trace caller → actor/owner/credential → sink → evidence. Exercise unauthorized and cross-principal negatives with temporary fake/local stores only. Record why Bind/approval is required or intentionally unnecessary; reproduce before any fix. |
| P1 — evaluator decision table | Existing 16 direct tests do not settle the malformed/contradictory validator-result and intent cases above | Focused tests using synthetic validator results and the real built-in validator; distinguish invalid internal contracts from externally reachable inputs. Separate any required fix from this inventory PR. |
| P1 — current audit provenance | Phase2 dynamically analyzes the checkout but emits a hardcoded historical `source_main`; its workflow asserts that historical value | Add a distinct observed tested SHA/tree/dirtiness provenance while preserving historical baseline fields/contracts. Prove the new identity matches the exact checkout, never relabel old proof as current. |
| P1 — inventory alignment | Six registry rows, five operator catalog targets and actual routes are different sets | Define a narrow cross-check for the five management targets, markers, helper calls and existing refusal tests. Fail on missing/extra members in that domain; do not infer universal coverage or expand frozen scope. |
| P1 — shared BFF identity | BFF role selection is separate from its shared backend key and tenant-bound backend guard | Design one end-to-end negative/positive matrix with explicit identity propagation assumptions; no customer credentials or live IdP required. Do not call UI admin recognition per-user backend identity. |
| P1 — independently operated IAM proof | Existing lab uses synthetic same-host source/target and explicit trusted keys | Separately agree one IAM-specific action, peer trust pin, allowed scope, stop conditions and evidence custody. Then normal success, direct bypass refusal, revoked/expired refusal and unknown-effect read-only reconciliation. No external run is authorized by this report. |
| P2 — reduce measured duplication | Existing audit tools and a provider-neutral boundary already exist | Select one same-contract helper/setup duplication only after consumer/semantic review; compare collection, rejection behavior and scoped CI timing. Retain version-specific acceptance and proof artifacts. |

Priorities here rank engineering work, not CVSS severity. This pass establishes
no new exploitable vulnerability. It does not close multi-host independence,
customer IAM, rollback/failover resistance, full tenant isolation, HA/DR or utility
recovery in the separate benchmark repository.

## Executed validation and reproducibility

On the pinned checkout, existing inventory scripts were rerun without importing
runtime code or executing candidates. No provider, IAM, Docker, DB migration,
restore, notification or other business operation was invoked.

```sh
python scripts/audit_large_consolidation.py --output /tmp/control-files.json
python scripts/audit_large_consolidation_phase2.py --output /tmp/control-phase2.json
PYTHONPATH=. python -m pytest -q \
  tests/governance/test_commit_boundary.py \
  tests/governance/test_runtime_authority_validation.py \
  tests/governance/test_authority_evidence_ingestion.py \
  tests/governance/test_bind_receipt_regulated_action_fields.py \
  veritas_os/tests/test_large_consolidation_audit_artifacts.py \
  veritas_os/tests/test_large_consolidation_audit_phase2.py
```

Result: **69 passed**, including all 16 direct commit-boundary tests; 12 existing
invalid-escape SyntaxWarnings from parsed CI-measurement source. No new tests or
CI gates are added for this documentation-only snapshot. Historical Phase2
`source_main` is preserved as a historical field, not used as the current source
pin. Counts and limits in this report come from the companion pinned Git-tree
index, not from a recursive scan of installed dependencies.

The extraction recipe for the source index follows below. Run it in a disposable
checkout of the exact source pin with Python 3.11+ and PyYAML; its only mutation
is writing the review index. It deliberately reads `git show` at HEAD rather
than executing scanned files. It is a snapshot recipe, not a new production
scanner or an authorization gate.

```python
import ast
import json
from pathlib import Path
import subprocess
import tomllib
import yaml

root = Path.cwd()
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
paths = sorted(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', source], text=True).splitlines())
def read(path):
    return subprocess.check_output(['git', 'show', f'{source}:{path}'], text=True)

routes, dynamic, scripts, handlers, background, workflows = [], [], [], [], [], []
python_paths = [p for p in paths if p.endswith('.py')]
for path in python_paths:
    tree = ast.parse(read(path), filename=path)
    if 'tests' in Path(path).parts or Path(path).name.startswith('test_'):
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test) in ("__name__ == '__main__'", "'__main__' == __name__"):
            scripts.append(path)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in ('do_GET', 'do_POST', 'do_PUT', 'do_DELETE', 'do_PATCH'):
                handlers.append({'file': path, 'line': node.lineno, 'handler': node.name})
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                if dec.func.attr not in ('get', 'post', 'put', 'patch', 'delete', 'websocket', 'api_route', 'route'):
                    continue
                if not dec.args or not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str) or not dec.args[0].value.startswith('/'):
                    continue
                routes.append({'file': path, 'line': node.lineno, 'method': dec.func.attr.upper(), 'path': dec.args[0].value, 'handler': node.name, 'declaration': ast.unparse(dec), 'bind_markers': [ast.unparse(d) for d in node.decorator_list if 'requires_bind_boundary' in ast.unparse(d)]})
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name.endswith(('.add_api_route', '.add_route', '.mount', '.add_websocket_route')):
                dynamic.append({'file': path, 'line': node.lineno, 'call': ast.unparse(node)})
            if name.split('.')[-1] in ('create_task', 'Thread', 'Timer', 'add_job', 'start_background_task'):
                background.append({'file': path, 'line': node.lineno, 'callee': name})
for path in paths:
    if path.startswith('.github/workflows/') and Path(path).suffix in ('.yml', '.yaml'):
        doc = yaml.load(read(path), Loader=yaml.BaseLoader)
        workflows.append({'file': path, 'events': doc.get('on'), 'jobs': sorted(doc.get('jobs', {}))})

data = {'source_main': source, 'status': 'STATIC_DISCOVERY_NOT_ENFORCEMENT_PROOF',
        'method': 'Git-tracked source bytes; AST literal route decorators, registration calls, main guards, selected background-call names; YAML job keys; no runtime imports',
        'limits': ['No arbitrary reflection, dynamic/plugin route enumeration, alias resolution, complete call graph, object ownership, effect classification or deployment discovery.', 'Route methods and marker presence do not establish side effects, active mounting, authorization correctness or bypass resistance.', 'Script, HTTP-handler and background matches are candidates; no match is not proof of absence.', 'Workflow definitions are not CI results; historical proof scopes remain separate.'],
        'counts': {'repository_python_files': len(python_paths), 'package_python_files': sum(p.startswith('veritas_os/') for p in python_paths), 'package_test_python_files': sum(p.startswith('veritas_os/tests/') for p in python_paths), 'root_test_python_files': sum(p.startswith('tests/') for p in python_paths)},
        'route_declarations': routes, 'registration_calls': dynamic,
        'project_scripts': tomllib.loads(read('pyproject.toml'))['project']['scripts'],
        'python_main_guard_files': sorted(set(scripts)),
        'shell_candidate_files': [p for p in paths if p.endswith('.sh')],
        'http_handler_candidates': handlers, 'background_call_candidates': background,
        'frontend_route_files': [p for p in paths if p.startswith('frontend/app/api/') and p.endswith('/route.ts')],
        'workflows': workflows}
dest = root / 'artifacts/consolidation-audit/2026-10-29-control-surface-index.json'
dest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: len(v) for k, v in data.items() if isinstance(v, list)}))
print(json.dumps(data['counts']))
```
