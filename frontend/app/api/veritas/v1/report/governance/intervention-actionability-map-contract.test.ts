import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { GET } from "./route";

const CONTRACT_EXCLUDED_SCOPE = [
  "automatic_enforcement",
  "automatic_blocking",
  "automatic_escalation",
  "scoring_model",
  "production_decisioning",
  "certification_claim",
] as const;

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../../../../..");
const FIXTURE_PATH = join(REPO_ROOT, "docs/en/demo/fixtures/intervention-actionability-map-v0.json");
const SCHEMA_PATH = join(REPO_ROOT, "docs/en/demo/schemas/intervention-actionability-map-v0.schema.json");

type InterventionActionabilityMapFixture = {
  version: string;
  purpose: string;
  actionability_model: string;
  scope: {
    included: string[];
    excluded: string[];
  };
  intervention_categories: Array<{
    id: string;
    label: string;
    description: string;
  }>;
  mappings: Array<{
    marker_id: string;
    source_layer: string;
    representative_phase: string;
    representative_failure_class?: string;
    recommended_action_ids: string[];
    evidence_to_preserve: string[];
    limitation: string;
  }>;
  validation_question: string;
  summary: Record<string, string>;
};

function loadJsonFixture(path: string): InterventionActionabilityMapFixture {
  return JSON.parse(readFileSync(path, "utf-8")) as InterventionActionabilityMapFixture;
}

function loadJsonDocument(path: string): Record<string, unknown> {
  return JSON.parse(readFileSync(path, "utf-8")) as Record<string, unknown>;
}

describe("Intervention Actionability Map v0 contract", () => {
  it("keeps the API map structurally stable and guidance-only", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        intervention_actionability_map: InterventionActionabilityMapFixture;
      };
    };
    const actionabilityMap = payload.governance_layer_snapshot.intervention_actionability_map;

    expect(actionabilityMap).toBeDefined();
    expect(actionabilityMap.version).toBe("v0");
    expect(actionabilityMap.actionability_model).toBe("deterministic_representative_intervention_guidance");
    expect(actionabilityMap.intervention_categories.length).toBeGreaterThan(0);
    expect(actionabilityMap.mappings.length).toBeGreaterThan(0);
    expect(actionabilityMap.validation_question.length).toBeGreaterThan(0);
    expect(typeof actionabilityMap.summary).toBe("object");

    for (const excludedScope of CONTRACT_EXCLUDED_SCOPE) {
      expect(actionabilityMap.scope.excluded).toContain(excludedScope);
    }

    const interventionCategoryIds = new Set(
      actionabilityMap.intervention_categories.map((category) => category.id),
    );
    for (const mapping of actionabilityMap.mappings) {
      expect(mapping.marker_id.length).toBeGreaterThan(0);
      expect(mapping.source_layer.length).toBeGreaterThan(0);
      expect(mapping.representative_phase.length).toBeGreaterThan(0);
      expect(mapping.recommended_action_ids.length).toBeGreaterThan(0);
      expect(mapping.evidence_to_preserve.length).toBeGreaterThan(0);
      expect(mapping.evidence_to_preserve.every((evidence) => evidence.length > 0)).toBe(true);
      expect(mapping.limitation.length).toBeGreaterThan(0);
      expect(mapping.limitation).toContain("does_not_claim");
      expect(mapping.limitation).toMatch(/automatic|runtime_enforcement/);

      for (const recommendedActionId of mapping.recommended_action_ids) {
        expect(interventionCategoryIds.has(recommendedActionId)).toBe(true);
      }
    }
  });

  it("matches the checked-in golden fixture", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        intervention_actionability_map: InterventionActionabilityMapFixture;
      };
    };
    const fixture = loadJsonFixture(FIXTURE_PATH);

    expect(payload.governance_layer_snapshot.intervention_actionability_map).toEqual(fixture);
  });

  it("keeps the schema contract focused on the v0 non-claim boundaries", () => {
    const schema = loadJsonDocument(SCHEMA_PATH);
    const schemaText = JSON.stringify(schema);

    expect(schemaText).toContain("deterministic_representative_intervention_guidance");
    expect(schemaText).toContain("does_not_claim");
    for (const excludedScope of CONTRACT_EXCLUDED_SCOPE) {
      expect(schemaText).toContain(excludedScope);
    }
  });
});
