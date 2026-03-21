"use client";

type BadgeVariant = "success" | "warning" | "danger" | "info" | "muted";

const VARIANT_STYLES: Record<BadgeVariant, string> = {
  success: "bg-success/20 text-success border-success/40",
  warning: "bg-warning/20 text-warning border-warning/40",
  danger: "bg-danger/20 text-danger border-danger/40",
  info: "bg-info/20 text-info border-info/40",
  muted: "bg-muted/20 text-muted-foreground border-border/40",
};

interface StatusBadgeProps {
  label: string;
  variant: BadgeVariant;
  className?: string;
}

export function StatusBadge({ label, variant, className }: StatusBadgeProps): JSX.Element {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${VARIANT_STYLES[variant]}${className ? ` ${className}` : ""}`}
    >
      {label}
    </span>
  );
}
