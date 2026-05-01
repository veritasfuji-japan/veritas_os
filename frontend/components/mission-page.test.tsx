import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRE_BIND_GOVERNANCE_VOCABULARY_LABELS } from "./dashboard-types";
import { I18nProvider } from "./i18n-provider";
import { MissionPage } from "./mission-page";

describe("MissionPage", () => {
  it("renders enhanced critical rail and global health summary", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Global Health Summary")).toBeInTheDocument();
    expect(screen.getByText("Current band:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Critical Rail")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText("Open incidents: 4")).toBeInTheDocument();
  });

  it("renders action-oriented priority cards", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText(/Why now/)).toHaveLength(3);
    expect(screen.getAllByText(/Impact window/)).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Decision で triage" })).toHaveAttribute("href", "/console");
  });

  it("surfaces trust-chain, governance, and evidence routing context", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Trust Chain Integrity")).toBeInTheDocument();
    expect(screen.getByText("Verification:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Governance approval risk")).toBeInTheDocument();
    expect(screen.getByText("Risk → Decision → Evidence → Report")).toBeInTheDocument();
    expect(screen.getByText("/health security posture (mandatory)")).toBeInTheDocument();
    expect(screen.getByText("Encryption algorithm:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Authentication mode:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Direct FUJI API:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("degraded:", { exact: false })).toBeInTheDocument();
  });

  it("renders pre-bind governance vocabulary and bind separation", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            intervention_viability: "minimal",
            concise_rationale: "early warning signal indicates reduced intervention headroom.",
            bind_outcome: "ESCALATED",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.heading)).toBeInTheDocument();
    expect(screen.getByText(/participation_state:/)).toBeInTheDocument();
    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
    expect(screen.getByText(/preservation_state:/)).toBeInTheDocument();
    expect(screen.getByText("degrading")).toBeInTheDocument();
    expect(screen.getByText(/intervention_viability:/)).toBeInTheDocument();
    expect(screen.getByText("minimal")).toBeInTheDocument();
    expect(screen.getByText(/bind_outcome:/)).toBeInTheDocument();
    expect(screen.getByText("ESCALATED")).toBeInTheDocument();
    expect(screen.getByText(/concise_rationale:/)).toBeInTheDocument();
  });

  it("uses shared pre-bind governance vocabulary labels", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            participation_state: "participatory",
            preservation_state: "open",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(`${PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.participation_state}:`)).toBeInTheDocument();
    expect(screen.getByText(`${PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.preservation_state}:`)).toBeInTheDocument();
  });

  it("omits governance timeline when additive pre-bind fields are absent", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{ bind_outcome: "COMMITTED" }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText(/Governance layer timeline/)).not.toBeInTheDocument();
    expect(screen.queryByText(/participation_state:/)).not.toBeInTheDocument();
  });

  it("renders governance artifact metadata for operators", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            pre_bind_detection_summary: { participation_state: "decision_shaping" },
            pre_bind_preservation_summary: { preservation_state: "degrading" },
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "Authority evidence missing",
            target_label: "Governance policy",
            operator_surface: "governance",
            relevant_ui_href: "/governance",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.getByText("AUTHORITY_MISSING")).toBeInTheDocument();
    expect(screen.getByText("Authority evidence missing")).toBeInTheDocument();
    expect(screen.getByText("Governance policy")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
    expect(screen.getByText("Operator actions")).toBeInTheDocument();
    expect(screen.getByText(/Open target surface:/)).toBeInTheDocument();
  });

  it.each(["/governance", "/governance/receipts/br_123", "/audit?receipt=br_123"])("renders safe relevant_ui_href as link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByRole("link", { name: href })[0]).toHaveAttribute("href", href);
  });

  it.each([
    "https://evil.example",
    "http://evil.example",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "//evil.example",
  ])("does not render external or protocol relevant_ui_href as a link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: href })).not.toBeInTheDocument();
    expect(screen.getByText(href)).toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });

  it.each(["/foo\\bar", "/foo\nbar", "/foo\tbar"])("does not render malformed relevant_ui_href as a link: %s", (href) => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
            relevant_ui_href: href,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: href })).not.toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });

  it("renders not available when relevant_ui_href is null", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "none",
            relevant_ui_href: null,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(/relevant_ui_href:/)).toBeInTheDocument();
    expect(screen.getAllByText("not available").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /relevant_ui_href/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Open target surface:/)).toBeInTheDocument();
    expect(screen.getAllByText(/not available/).length).toBeGreaterThan(0);
  });

  it("renders target surface action as link only when relevant_ui_href is safe", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            target_label: "Governance policy",
            relevant_ui_href: "/governance",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
  });

  it("does not render target surface action link when relevant_ui_href is unsafe", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            relevant_ui_href: "https://evil.example",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: "https://evil.example" })).not.toBeInTheDocument();
    expect(screen.getByText(/unsafe or external link not rendered/)).toBeInTheDocument();
  });

  it("renders bind receipt id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            bind_receipt_id: "br_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Review bind receipt:")).toBeInTheDocument();
    expect(screen.getByText("br_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "br_123" })).toHaveAttribute("href", "/audit?bind_receipt_id=br_123");
  });

  it("renders decision id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            decision_id: "dec_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View decision artifact:")).toBeInTheDocument();
    expect(screen.getByText("dec_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "dec_123" })).toHaveAttribute("href", "/audit?decision_id=dec_123");
  });

  it("renders execution intent id as audit link when id is valid", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            execution_intent_id: "ei_123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View execution intent:")).toBeInTheDocument();
    expect(screen.getByText("ei_123")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ei_123" })).toHaveAttribute("href", "/audit?execution_intent_id=ei_123");
  });

  it("covers demo-grade Mission Control artifact review actions with safe audit links only", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            decision_id: "dec_demo_001",
            bind_receipt_id: "br_demo_001",
            execution_intent_id: "ei_demo_001",
            pre_bind_source: "trustlog_matching_decision",
            bind_reason_code: "AUTHORITY_MISSING",
            bind_failure_reason: "Authority evidence missing",
            target_label: "Governance policy",
            relevant_ui_href: "/governance",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Governance artifacts")).toBeInTheDocument();
    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.getByText("AUTHORITY_MISSING")).toBeInTheDocument();
    expect(screen.getByText("Authority evidence missing")).toBeInTheDocument();
    expect(screen.getByText("Governance policy")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "/governance" })[0]).toHaveAttribute("href", "/governance");
    expect(screen.getByRole("link", { name: "br_demo_001" })).toHaveAttribute("href", "/audit?bind_receipt_id=br_demo_001");
    expect(screen.getByRole("link", { name: "dec_demo_001" })).toHaveAttribute("href", "/audit?decision_id=dec_demo_001");
    expect(screen.getByRole("link", { name: "ei_demo_001" })).toHaveAttribute("href", "/audit?execution_intent_id=ei_demo_001");
    expect(screen.queryByRole("link", { name: "/decisions/dec_demo_001" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "/execution-intents/ei_demo_001" })).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="/trustlog"]')).toBeNull();
  });


  it("does not create audit links for invalid artifact ids", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            bind_receipt_id: "../secret",
            decision_id: "javascript:alert(1)",
            execution_intent_id: "ei\n123",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByRole("link", { name: "../secret" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "javascript:alert(1)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /ei/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/route unavailable/).length).toBeGreaterThan(0);
  });
it("shows pre-bind source without creating a fake trustlog route", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "trustlog_matching_decision",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("View pre-bind source:")).toBeInTheDocument();
    expect(screen.getAllByText("trustlog_matching_decision").length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /trustlog_matching_decision/i })).not.toBeInTheDocument();
  });

  it("renders fallback text for null pre-bind summaries", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "none",
            pre_bind_detection_summary: null,
            pre_bind_preservation_summary: null,
            bind_reason_code: null,
            bind_failure_reason: null,
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("none").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No pre-bind summary available").length).toBeGreaterThan(0);
  });

  it("shows degraded pre-bind source markers without crashing", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            pre_bind_source: "malformed_pre_bind_artifact",
            participation_state: "unknown",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText("malformed_pre_bind_artifact").length).toBeGreaterThan(0);
    expect(screen.getByText(/classification: degraded/)).toBeInTheDocument();
  });

  it("renders governance observation fields when payload includes governance_observation", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            governance_observation: {
              policy_mode: "observe",
              environment: "development",
              would_have_blocked: true,
              would_have_blocked_reason: "policy_violation:missing_authority_evidence",
              effective_outcome: "proceed",
              observed_outcome: "block",
              operator_warning: true,
              audit_required: true,
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Governance observation")).toBeInTheDocument();
    expect(screen.getByText("observe")).toBeInTheDocument();
    expect(screen.getByText("development")).toBeInTheDocument();
    expect(screen.getByText("would_have_blocked")).toBeInTheDocument();
    expect(screen.getAllByText("true").length).toBeGreaterThan(0);
    expect(screen.getByText("policy_violation:missing_authority_evidence")).toBeInTheDocument();
    expect(screen.getByText("effective_outcome")).toBeInTheDocument();
    expect(screen.getByText("proceed")).toBeInTheDocument();
    expect(screen.getByText("observed_outcome")).toBeInTheDocument();
    expect(screen.getByText("block")).toBeInTheDocument();
    expect(screen.getByText("operator_warning")).toBeInTheDocument();
    expect(screen.getByText("audit_required")).toBeInTheDocument();
  });

  it("does not render governance observation section when governance_observation is absent", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{}}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText("Governance observation")).not.toBeInTheDocument();
    expect(screen.getByText("Governance artifacts")).toBeInTheDocument();
  });

  it("renders enforce mode governance observation fields", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            governance_observation: {
              policy_mode: "enforce",
              environment: "production",
              would_have_blocked: false,
              effective_outcome: "block",
              observed_outcome: "block",
              operator_warning: false,
              audit_required: true,
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("enforce")).toBeInTheDocument();
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("would_have_blocked")).toBeInTheDocument();
    expect(screen.getAllByText("false").length).toBeGreaterThan(0);
  });
});
