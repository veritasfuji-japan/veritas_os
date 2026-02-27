export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
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

export interface PipelineStepView {
  name: string;
  summary: string;
  status: "complete" | "idle";
  detail: string;
}

export interface GovernanceDriftAlert {
  title: string;
  description: string;
}
