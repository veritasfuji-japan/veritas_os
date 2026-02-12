import { Button, Card } from "@veritas/design-system";
import type { HealthResponse } from "@veritas/types";

const sampleHealth: HealthResponse = {
  status: "ok",
  service: "frontend",
  timestamp: new Date().toISOString()
};

export default function Home(): JSX.Element {
  return (
    <div className="flex flex-col gap-4">
      <Card title="Layer0 Design System Ready">
        <p className="text-muted-foreground">
          frontend は packages/design-system のトークン・テーマ・アクセシビリティ基盤を利用しています。
        </p>
        <pre className="font-audit mt-4 rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(sampleHealth, null, 2)}
        </pre>
        <Button aria-label="デザインシステム動作確認" className="mt-4">
          Accessible action
        </Button>
      </Card>
    </div>
  );
}
