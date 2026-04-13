import { afterEach, describe, expect, it, vi } from "vitest";

import {
  normalizeViolation,
  POST,
  resetDedupStateForTest,
} from "./route";

import { NextRequest } from "next/server";

function makeRequest(
  body: unknown,
  contentType = "application/csp-report",
): NextRequest {
  const init: RequestInit = {
    method: "POST",
    headers: { "Content-Type": contentType },
    body: typeof body === "string" ? body : JSON.stringify(body),
  };
  return new NextRequest("http://localhost:3000/api/veritas/csp-report", init);
}

describe("CSP report endpoint", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetDedupStateForTest();
  });

  // ---------- normalizeViolation ----------

  describe("normalizeViolation", () => {
    it("parses legacy csp-report format", () => {
      const result = normalizeViolation({
        "csp-report": {
          "violated-directive": "script-src 'self'",
          "blocked-uri": "https://evil.example.com/bad.js",
          "document-uri": "https://app.example.com/page",
          "source-file": "https://app.example.com/page",
        },
      });

      expect(result).toEqual({
        directive: "script-src 'self'",
        blockedUri: "https://evil.example.com/bad.js",
        documentUri: "https://app.example.com/page",
        sourceFile: "https://app.example.com/page",
      });
    });

    it("parses modern Reporting API format", () => {
      const result = normalizeViolation([
        {
          type: "csp-violation",
          body: {
            effectiveDirective: "script-src-elem",
            blockedURL: "inline",
            documentURL: "https://app.example.com/",
            sourceFile: "",
          },
        },
      ]);

      expect(result).toEqual({
        directive: "script-src-elem",
        blockedUri: "inline",
        documentUri: "https://app.example.com/",
        sourceFile: "",
      });
    });

    it("parses flat object fallback", () => {
      const result = normalizeViolation({
        "effective-directive": "style-src-elem",
        "blocked-uri": "blob:",
        "document-uri": "https://app.example.com/",
        "source-file": "",
      });

      expect(result).toEqual({
        directive: "style-src-elem",
        blockedUri: "blob:",
        documentUri: "https://app.example.com/",
        sourceFile: "",
      });
    });

    it("returns null for unrecognised payload", () => {
      expect(normalizeViolation({ random: "data" })).toBeNull();
      expect(normalizeViolation(null)).toBeNull();
      expect(normalizeViolation("string")).toBeNull();
    });
  });

  // ---------- POST handler ----------

  describe("POST handler", () => {
    it("returns 204 for valid legacy CSP report", async () => {
      const res = await POST(
        makeRequest({
          "csp-report": {
            "violated-directive": "script-src 'self'",
            "blocked-uri": "https://evil.example.com/bad.js",
            "document-uri": "https://app.example.com/page",
          },
        }),
      );

      expect(res.status).toBe(204);
    });

    it("returns 204 for valid modern Reporting API payload", async () => {
      const res = await POST(
        makeRequest(
          [
            {
              type: "csp-violation",
              body: {
                effectiveDirective: "script-src-elem",
                blockedURL: "inline",
                documentURL: "https://app.example.com/",
              },
            },
          ],
          "application/reports+json",
        ),
      );

      expect(res.status).toBe(204);
    });

    it("returns 204 for malformed JSON body", async () => {
      const res = await POST(makeRequest("not json {{{", "application/json"));

      expect(res.status).toBe(204);
    });

    it("returns 204 for empty body", async () => {
      const res = await POST(makeRequest("", "application/csp-report"));

      expect(res.status).toBe(204);
    });

    it("returns 413 for oversized content-length", async () => {
      const req = new NextRequest(
        "http://localhost:3000/api/veritas/csp-report",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/csp-report",
            "Content-Length": String(100 * 1024),
          },
          body: "{}",
        },
      );
      const res = await POST(req);

      expect(res.status).toBe(413);
    });

    it("deduplicates identical violations within the dedup window", async () => {
      const spy = vi.spyOn(console, "info").mockImplementation(() => {});

      const body = {
        "csp-report": {
          "violated-directive": "script-src",
          "blocked-uri": "inline",
          "document-uri": "https://app.example.com/",
        },
      };

      await POST(makeRequest(body));
      await POST(makeRequest(body));
      await POST(makeRequest(body));

      // Only one log call despite three requests
      expect(spy).toHaveBeenCalledTimes(1);
      spy.mockRestore();
    });

    it("logs different violations separately", async () => {
      const spy = vi.spyOn(console, "info").mockImplementation(() => {});

      await POST(
        makeRequest({
          "csp-report": {
            "violated-directive": "script-src",
            "blocked-uri": "inline",
            "document-uri": "https://a.example.com/",
          },
        }),
      );

      await POST(
        makeRequest({
          "csp-report": {
            "violated-directive": "style-src",
            "blocked-uri": "blob:",
            "document-uri": "https://b.example.com/",
          },
        }),
      );

      expect(spy).toHaveBeenCalledTimes(2);
      spy.mockRestore();
    });
  });
});
