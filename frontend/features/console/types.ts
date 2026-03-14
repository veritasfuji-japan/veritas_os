import { type PipelineStageName } from "./constants";

export interface ChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
}

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
}

export interface DecisionAlternativeView {
  optionSummary: string;
  tradeOff: string;
  relativeWeakness: string;
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

export interface GovernanceDriftAlert {
  title: string;
  description: string;
}
