"use client";

import { useEffect, useState } from "react";
import { Button, Card } from "@veritas/design-system";
import type { HealthResponse } from "@veritas/types";

type BackendHealthState = {
  ok: boolean;
  message: string;
};

const sampleHealth: HealthResponse = {
  status: "ok",
  service: "frontend",
  timestamp: new Date().toISOString()
};

/**
 * Fetch backend health from the configured public API base URL.
 *
 * The URL must be provided by NEXT_PUBLIC_API_BASE_URL so that
 * compose and local development can target different backends safely.
 */
async function checkBackendHealth(): Promise<BackendHealthState> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!apiBaseUrl) {
    return {
      ok: false,
      message: "NEXT_PUBLIC_API_BASE_URL is not configured"
    };
  }

  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) {
      return {
        ok: false,
        message: `backend health request failed (${response.status})`
      };
    }

    const data = (await response.json()) as HealthResponse;
    return {
      ok: true,
      message: `${data.service ?? "backend"}: ${data.status}`
    };
  } catch {
    return {
      ok: false,
      message: "backend unreachable"
    };
  }
}

export default function Home(): JSX.Element {
  const [backendHealth, setBackendHealth] = useState<BackendHealthState>({
    ok: false,
    message: "checking backend..."
  });

  useEffect(() => {
    let active = true;

    const run = async (): Promise<void> => {
      const nextState = await checkBackendHealth();
      if (active) {
        setBackendHealth(nextState);
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <Card title="Layer0 Design System Ready">
        <p className="text-muted-foreground">
          frontend は packages/design-system のトークン・テーマ・アクセシビリティ基盤を利用しています。
        </p>
        <pre className="font-audit mt-4 rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(sampleHealth, null, 2)}
        </pre>
        <p aria-live="polite" className="mt-4 text-sm">
          backend connection: {backendHealth.message}
        </p>
        <Button aria-label="デザインシステム動作確認" className="mt-4">
          Accessible action
        </Button>
      </Card>
    </div>
  );
}
