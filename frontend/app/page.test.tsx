import { render, screen, waitFor } from "@testing-library/react";
import Home from "./page";

describe("Home", () => {
  beforeEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://backend:8000";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  });

  it("renders layer0 card", () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ service: "backend", status: "ok" })
    } as Response);

    render(<Home />);
    expect(screen.getByText("Layer0 Design System Ready")).toBeInTheDocument();
    expect(screen.getByLabelText("デザインシステム動作確認")).toBeInTheDocument();
  });

  it("shows backend health status", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ service: "backend", status: "ok" })
    } as Response);

    render(<Home />);

    await waitFor(() => {
      expect(
        screen.getByText("backend connection: backend: ok")
      ).toBeInTheDocument();
    });
  });
});
