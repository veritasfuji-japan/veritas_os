import { render, screen } from "@testing-library/react";
import Home from "./page";

describe("Home", () => {
  it("renders layer0 card", () => {
    render(<Home />);
    expect(screen.getByText("Layer0 Design System Ready")).toBeInTheDocument();
    expect(screen.getByLabelText("デザインシステム動作確認")).toBeInTheDocument();
  });
});
