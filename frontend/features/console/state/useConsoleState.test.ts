import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useConsoleState } from "./useConsoleState";
import { buildGovernanceDriftAlert } from "../analytics/pipeline";

vi.mock("../analytics/pipeline", () => ({
  buildGovernanceDriftAlert: vi.fn(() => null),
}));

const mockedBuildAlert = vi.mocked(buildGovernanceDriftAlert);

describe("useConsoleState", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("returns initial state", () => {
    const { result } = renderHook(() => useConsoleState());

    expect(result.current.query).toBe("");
    expect(result.current.result).toBeNull();
    expect(result.current.chatMessages).toEqual([]);
    expect(result.current.showDriftAlert).toBe(false);
  });

  it("updates query via setQuery", () => {
    const { result } = renderHook(() => useConsoleState());

    act(() => {
      result.current.setQuery("new query");
    });

    expect(result.current.query).toBe("new query");
  });

  it("shows drift alert when buildGovernanceDriftAlert returns a value", () => {
    mockedBuildAlert.mockReturnValue({ level: "warning", message: "drift detected" } as never);

    const { result } = renderHook(() => useConsoleState());

    act(() => {
      result.current.setResult({ ok: true } as never);
    });

    expect(result.current.showDriftAlert).toBe(true);
    expect(result.current.governanceDriftAlert).toEqual({
      level: "warning",
      message: "drift detected",
    });
  });

  it("hides drift alert after 8 seconds", () => {
    mockedBuildAlert.mockReturnValue({ level: "warning", message: "drift detected" } as never);

    const { result } = renderHook(() => useConsoleState());

    act(() => {
      result.current.setResult({ ok: true } as never);
    });

    expect(result.current.showDriftAlert).toBe(true);

    act(() => {
      vi.advanceTimersByTime(8000);
    });

    expect(result.current.showDriftAlert).toBe(false);
  });
});
