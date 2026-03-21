"use client";

interface ToggleRowProps {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}

export function ToggleRow({ label, checked, onChange, disabled }: ToggleRowProps): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3.5 py-2.5 text-sm">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-label={label}
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={["relative inline-flex h-5 w-10 items-center rounded-full transition-colors", checked ? "bg-primary" : "bg-muted", disabled ? "opacity-50 cursor-not-allowed" : ""].join(" ")}
      >
        <span className={["inline-block h-4 w-4 rounded-full bg-white transition-transform", checked ? "translate-x-5" : "translate-x-0.5"].join(" ")} />
      </button>
    </div>
  );
}
