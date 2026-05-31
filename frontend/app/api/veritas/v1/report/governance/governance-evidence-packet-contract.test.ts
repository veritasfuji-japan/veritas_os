import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { GET } from "./route";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../../../../../..");
const FIXTURE_PATH = join(REPO_ROOT, "docs/en/demo/fixtures/governance-evidence-packet-v0.json");
const SCHEMA_PATH = join(REPO_ROOT, "docs/en/demo/schemas/governance-evidence-packet-v0.schema.json");

const REQUIRED_SECTION_IDS = [
  "trajectory_summary",
  "dynamic_degradation_summary",
  "irreversibility_summary",
  "recognition_gap_summary",
  "governance_attack_surface_summary",
  "safeguard_coverage_summary",
  "intervention_actionability_summary",
] as const;

const REQUIRED_REVIEWER_QUESTIONS = [
  "What was the bind outcome?",
  "What decision-space narrowing occurred before bind?",
  "When did intervention viability begin degrading?",
  "Where was the last meaningful intervention point?",
  "Did actor recognition lag behind structural degradation?",
  "Which governance attack surfaces were relevant?",
  "Which safeguards made those surfaces visible?",
  "Which intervention categories were representative?",
  "What does this packet not claim?",
] as const;

const REQUIRED_PRESERVED_EVIDENCE_REFS = [
  "governance_layer_snapshot.trajectory_shaping_lineage",
  "governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case",
  "governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon",
  "governance_layer_snapshot.trajectory_shaping_lineage.dynamic_conditions_validation_case.irreversibility_horizon.actor_recognition_gap",
  "governance_layer_snapshot.governance_attack_surface_registry",
  "governance_layer_snapshot.governance_attack_surface_registry.safeguard_coverage_matrix",
  "governance_layer_snapshot.intervention_actionability_map",
] as const;

const REQUIRED_LIMITATIONS = [
  "not_certification",
  "not_production_security_guarantee",
  "not_automatic_enforcement",
  "not_automatic_attack_detection",
  "not_scoring_model",
  "not_legal_conclusion",
  "representative_demo_packet_only",
] as const;

const FORBIDDEN_CLAIM_PHRASES = [
  "certified",
  "certification guaranteed",
  "production security guaranteed",
  "automatic enforcement enabled",
  "legal conclusion",
  "formal verification complete",
  "complete prevention guaranteed",
] as const;

type JsonSchema = {
  $ref?: string;
  type?: "object" | "array" | "string";
  const?: unknown;
  enum?: unknown[];
  required?: string[];
  properties?: Record<string, JsonSchema>;
  additionalProperties?: boolean;
  minLength?: number;
  minItems?: number;
  items?: JsonSchema;
  contains?: JsonSchema;
  allOf?: JsonSchema[];
  $defs?: Record<string, JsonSchema>;
};

type GovernanceEvidencePacketFixture = {
  version: string;
  packet_id: string;
  packet_model: string;
  purpose: string;
  generated_from: {
    scenario_id: string;
    source_payload: string;
  };
  decision_context_summary: Record<string, string>;
  packet_sections: Array<{
    id: string;
    source_layer: string;
    title: string;
    key_points: string[];
    evidence_refs: string[];
  }>;
  reviewer_questions: string[];
  preserved_evidence_refs: string[];
  limitations: string[];
  summary: {
    concise: string;
    operator: string;
  };
};

function loadJsonFixture(path: string): GovernanceEvidencePacketFixture {
  return JSON.parse(readFileSync(path, "utf-8")) as GovernanceEvidencePacketFixture;
}

function loadJsonSchema(path: string): JsonSchema {
  return JSON.parse(readFileSync(path, "utf-8")) as JsonSchema;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function resolveRef(schema: JsonSchema, rootSchema: JsonSchema): JsonSchema {
  if (!schema.$ref) {
    return schema;
  }

  const prefix = "#/$defs/";
  expect(schema.$ref.startsWith(prefix)).toBe(true);
  const definitionName = schema.$ref.slice(prefix.length);
  const resolved = rootSchema.$defs?.[definitionName];
  expect(resolved, `Missing schema definition: ${schema.$ref}`).toBeDefined();
  return resolved as JsonSchema;
}

function validateSchema(schema: JsonSchema, value: unknown, rootSchema: JsonSchema, path = "$ "): string[] {
  const resolvedSchema = resolveRef(schema, rootSchema);
  const errors: string[] = [];

  if (Object.prototype.hasOwnProperty.call(resolvedSchema, "const") && value !== resolvedSchema.const) {
    errors.push(`${path}must equal ${String(resolvedSchema.const)}`);
  }

  if (resolvedSchema.enum && !resolvedSchema.enum.includes(value)) {
    errors.push(`${path}must be one of ${resolvedSchema.enum.join(", ")}`);
  }

  if (resolvedSchema.type === "object" && !isRecord(value)) {
    errors.push(`${path}must be an object`);
    return errors;
  }

  if (resolvedSchema.type === "array" && !Array.isArray(value)) {
    errors.push(`${path}must be an array`);
    return errors;
  }

  if (resolvedSchema.type === "string" && typeof value !== "string") {
    errors.push(`${path}must be a string`);
    return errors;
  }

  if (typeof value === "string" && resolvedSchema.minLength && value.length < resolvedSchema.minLength) {
    errors.push(`${path}must not be empty`);
  }

  if (Array.isArray(value)) {
    if (resolvedSchema.minItems && value.length < resolvedSchema.minItems) {
      errors.push(`${path}must contain at least ${resolvedSchema.minItems} items`);
    }

    if (resolvedSchema.items) {
      value.forEach((item, index) => {
        errors.push(...validateSchema(resolvedSchema.items as JsonSchema, item, rootSchema, `${path}[${index}]`));
      });
    }

    if (resolvedSchema.contains) {
      const containsMatch = value.some(
        (item) => validateSchema(resolvedSchema.contains as JsonSchema, item, rootSchema, path).length === 0,
      );
      if (!containsMatch) {
        errors.push(`${path}must contain required schema match`);
      }
    }
  }

  if (isRecord(value)) {
    for (const requiredProperty of resolvedSchema.required ?? []) {
      if (!Object.prototype.hasOwnProperty.call(value, requiredProperty)) {
        errors.push(`${path}.${requiredProperty} is required`);
      }
    }

    if (resolvedSchema.additionalProperties === false && resolvedSchema.properties) {
      for (const propertyName of Object.keys(value)) {
        if (!Object.prototype.hasOwnProperty.call(resolvedSchema.properties, propertyName)) {
          errors.push(`${path}.${propertyName} is not allowed`);
        }
      }
    }

    for (const [propertyName, propertySchema] of Object.entries(resolvedSchema.properties ?? {})) {
      if (Object.prototype.hasOwnProperty.call(value, propertyName)) {
        errors.push(...validateSchema(propertySchema, value[propertyName], rootSchema, `${path}.${propertyName}`));
      }
    }
  }

  for (const subSchema of resolvedSchema.allOf ?? []) {
    errors.push(...validateSchema(subSchema, value, rootSchema, path));
  }

  return errors;
}

describe("Governance Evidence Packet v0 contract", () => {
  it("validates the API packet against the checked-in JSON Schema", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        governance_evidence_packet: GovernanceEvidencePacketFixture;
      };
    };
    const packet = payload.governance_layer_snapshot.governance_evidence_packet;
    const schema = loadJsonSchema(SCHEMA_PATH);

    expect(validateSchema(schema, packet, schema)).toEqual([]);
  });

  it("matches the checked-in golden fixture", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        governance_evidence_packet: GovernanceEvidencePacketFixture;
      };
    };
    const fixture = loadJsonFixture(FIXTURE_PATH);

    expect(payload.governance_layer_snapshot.governance_evidence_packet).toEqual(fixture);
  });

  it("keeps required packet structure, evidence refs, and non-claims present", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        governance_evidence_packet: GovernanceEvidencePacketFixture;
      };
    };
    const packet = payload.governance_layer_snapshot.governance_evidence_packet;

    expect(packet.version).toBe("v0");
    expect(packet.packet_id).toBe("pre_boundary_collapse_governance_evidence_packet_v0");
    expect(packet.packet_model).toBe("deterministic_representative_reviewer_packet");
    expect(packet.generated_from).toEqual({
      scenario_id: "pre_boundary_collapse",
      source_payload: "governance_layer_snapshot",
    });
    expect(packet.decision_context_summary).toMatchObject({
      bind_outcome: "FORMALLY_VALID_STRUCTURALLY_COLLAPSED",
      participation_signal: "decision_shaping",
      preservation_state: "collapsed",
      intervention_viability: "lost",
      decision_space_state: "structurally_narrowed_before_bind",
    });

    expect(packet.packet_sections.map((section) => section.id)).toEqual(
      expect.arrayContaining([...REQUIRED_SECTION_IDS]),
    );
    expect(packet.reviewer_questions).toEqual(expect.arrayContaining([...REQUIRED_REVIEWER_QUESTIONS]));
    expect(packet.preserved_evidence_refs).toEqual(expect.arrayContaining([...REQUIRED_PRESERVED_EVIDENCE_REFS]));
    expect(packet.limitations).toEqual(expect.arrayContaining([...REQUIRED_LIMITATIONS]));

    for (const section of packet.packet_sections) {
      expect(section.key_points.length).toBeGreaterThan(0);
      expect(section.evidence_refs.length).toBeGreaterThan(0);
    }
  });

  it("blocks forbidden overclaim phrases from the packet payload", async () => {
    const response = await GET(
      new Request("http://localhost/api/veritas/v1/report/governance?demo_scenario=pre_boundary_collapse"),
    );

    expect(response.status).toBe(200);
    const payload = await response.json() as {
      governance_layer_snapshot: {
        governance_evidence_packet: GovernanceEvidencePacketFixture;
      };
    };
    const packetText = JSON.stringify(payload.governance_layer_snapshot.governance_evidence_packet).toLowerCase();

    for (const forbiddenPhrase of FORBIDDEN_CLAIM_PHRASES) {
      expect(packetText).not.toContain(forbiddenPhrase);
    }
  });
});
