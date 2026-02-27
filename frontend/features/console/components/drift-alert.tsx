import { type GovernanceDriftAlert } from "../types";

interface DriftAlertProps {
  alert: GovernanceDriftAlert | null;
  showAlert: boolean;
  setShowAlert: (next: boolean | ((prev: boolean) => boolean)) => void;
}

export function DriftAlert({ alert, showAlert, setShowAlert }: DriftAlertProps): JSX.Element | null {
  if (!alert) {
    return null;
  }

  return (
    <div className="fixed bottom-4 left-4 z-40 flex flex-col gap-2">
      <button
        type="button"
        className="w-fit rounded-full border border-amber-400/70 bg-amber-500/15 px-3 py-1 text-xs font-semibold text-amber-200"
        onClick={() => setShowAlert((prev) => !prev)}
      >
        {alert.title}
      </button>
      {showAlert ? (
        <aside role="alert" className="max-w-xs rounded-md border border-amber-400/60 bg-background/95 p-3 text-xs shadow-xl">
          <p className="font-semibold text-amber-300">Drift Alert</p>
          <p className="mt-1 text-foreground">{alert.description}</p>
        </aside>
      ) : null}
    </div>
  );
}
