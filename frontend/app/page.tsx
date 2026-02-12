import { Button, Card } from "@veritas/design-system";
import type { HealthResponse } from "@veritas/types";

const sampleHealth: HealthResponse = {
  status: "ok",
  service: "frontend",
  timestamp: new Date().toISOString()
};

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-4 p-6">
      <Card title="Veritas UI Workspace">
        <p className="text-sm text-muted-foreground">
          frontend は packages/types と packages/design-system を参照できています。
        </p>
        <pre className="mt-4 rounded-md bg-muted p-3 text-xs">{JSON.stringify(sampleHealth, null, 2)}</pre>
        <Button className="mt-4">shadcn/ui style button</Button>
      </Card>
    </main>
  );
}
