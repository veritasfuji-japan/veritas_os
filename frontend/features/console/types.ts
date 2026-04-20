import { type PipelineStageName } from "./constants";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
}

export type ConsoleExecutionStatus =
  | "idle"
  | "submitting"
  | "streaming"
  | "completed"
  | "failed"
  | "timeout";

export interface StepAnalytics {
  name: string;
  executed: boolean;
  uncertaintyBefore: number | null;
  uncertaintyAfter: number | null;
  tokenCost: number | null;
  inferred: boolean;
}

export interface CostBenefitAnalytics {
  steps: StepAnalytics[];
  totalTokenCost: number;
  uncertaintyReduction: number | null;
  inferred: boolean;
}

export type PipelineStageStatus = "idle" | "running" | "complete" | "warning" | "failed";

export interface PipelineStepView {
  name: string;
  summary: string;
  status: PipelineStageStatus;
  detail: string;
}

export interface PipelineStageView {
  name: PipelineStageName;
  summary: string;
  status: PipelineStageStatus;
  detail: string;
  latencyMs: number | null;
  raw: Record<string, unknown>;
}

export interface FujiGateView {
  decision: string;
  ruleHit: string;
  severity: string;
  remediationHint: string;
  riskyFragmentPreview: string;
}

export interface DecisionChosenView {
  finalDecision: string;
  whyChosen: string;
  supportingEvidenceSummary: string;
  valueRationale: string;
  /** Value total score (0-1) when available from backend. */
  valueScore: number | null;
}

export interface DecisionAlternativeView {
  optionSummary: string;
  tradeOff: string;
  relativeWeakness: string;
  /** Per-alternative value score (0-1) when the backend provides it. */
  valueScore: number | null;
}

export interface DecisionRejectedReasonsView {
  fujiBlock: string;
  weakEvidence: string;
  poorDebateOutcome: string;
  valueConflict: string;
}

export interface DecisionResultView {
  chosen: DecisionChosenView;
  alternatives: DecisionAlternativeView[];
  rejectedReasons: DecisionRejectedReasonsView;
}

export type BindOutcomeStatus = "COMMITTED" | "BLOCKED" | "ESCALATED" | "ROLLED_BACK" | "UNKNOWN";

export interface BindCheckBreakdownView {
  authority: string;
  constraints: string;
  drift: string;
  risk: string;
}

export interface BindPhaseView {
  decisionPhase: string;
  bindPhase: BindOutcomeStatus;
  bindReceiptId: string;
  executionIntentId: string;
  bindFailureReason: string;
  bindReasonCode: string;
  checks: BindCheckBreakdownView;
}

export type ConsoleViewerRole = "auditor" | "operator" | "developer";

export interface RuntimeStatusView {
  activePosture: string;
  backend: string;
  verifyStatus: string;
}

export interface EvidenceBundleDraft {
  requestId: string;
  generatedAt: string;
  gateDecision: string;
  businessDecision: string;
  nextAction: string;
  humanReviewRequired: boolean;
  requiredEvidence: string[];
  missingEvidence: string[];
  runtimeStatus: RuntimeStatusView;
}
export interface PublicDecisionSchemaView {
  gateDecision: string;
  gateDecisionLabel: string;
  businessDecision: string;
  nextAction: string;
  requiredEvidence: string[];
  missingEvidence: string[];
  humanReviewRequired: boolean;
  activePosture: string;
  backend: string;
  verifyStatus: string;
}

export interface FujiViolationView {
  rule: string;
  detail: string;
  severity: string;
}

export interface FujiGateDetailView {
  decision: string;
  ruleHit: string;
  severity: string;
  remediationHint: string;
  riskyFragmentPreview: string;
  riskScore: number | null;
  reasons: string[];
  violations: FujiViolationView[];
}

export interface GovernanceDriftAlert {
  title: string;
  description: string;
}
