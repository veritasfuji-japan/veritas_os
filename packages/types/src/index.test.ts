import type { HealthResponse } from "./index";

describe("types", () => {
  it("accepts a valid health response shape", () => {
    const response: HealthResponse = {
      status: "ok",
      service: "api",
      timestamp: "2026-01-01T00:00:00.000Z"
    };

    expect(response.status).toBe("ok");
  });
});
