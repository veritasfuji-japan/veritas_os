import { describe, it, expect } from "vitest";
import {
  STREAM_WINDOW_MS,
  ALERT_CLUSTER_THRESHOLD,
  SEVERITY_CLASSES,
  STATUS_LABELS,
} from "./constants";

describe("risk constants", () => {
  it("STREAM_WINDOW_MS is 24 hours", () => {
    expect(STREAM_WINDOW_MS).toBe(24 * 60 * 60 * 1000);
  });

  it("ALERT_CLUSTER_THRESHOLD is 0.82", () => {
    expect(ALERT_CLUSTER_THRESHOLD).toBe(0.82);
  });

  it("SEVERITY_CLASSES covers all severities", () => {
    expect(SEVERITY_CLASSES.critical).toContain("danger");
    expect(SEVERITY_CLASSES.high).toContain("warning");
    expect(SEVERITY_CLASSES.medium).toContain("info");
    expect(SEVERITY_CLASSES.low).toContain("muted");
  });

  it("STATUS_LABELS covers all request statuses", () => {
    expect(STATUS_LABELS.active).toBe("Active");
    expect(STATUS_LABELS.mitigated).toBe("Mitigated");
    expect(STATUS_LABELS.investigating).toBe("Investigating");
    expect(STATUS_LABELS.new).toBe("New");
  });
});
