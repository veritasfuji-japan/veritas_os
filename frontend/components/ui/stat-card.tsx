"use client";

interface StatCardProps {
  label: string;
  value: string | number;
  variant?: "default" | "success" | "danger" | "warning" | "info";
  className?: string;
}

const VALUE_STYLES: Record<NonNullable<StatCardProps["variant"]>, string> = {
  default: "text-foreground",
  success: "text-success",
  danger: "text-danger",
  warning: "text-warning",
  info: "text-info",
};

export function StatCard({ label, value, variant = "default", className }: StatCardProps): JSX.Element {
  return (
    <div className={`rounded border border-border px-3 py-2 text-center${className ? ` ${className}` : ""}`}>
      <p className={`text-lg font-semibold ${VALUE_STYLES[variant]}`}>{value}</p>
      <p className="text-2xs text-muted-foreground">{label}</p>
    </div>
  );
}
