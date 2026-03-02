import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "./utils";

const cardVariants = cva(
  "w-full rounded-xl border bg-surface shadow-sm transition-shadow",
  {
    variants: {
      variant: {
        default: "border-border bg-surface",
        elevated: "border-border/50 bg-surface shadow-md",
        ghost: "border-transparent bg-transparent shadow-none",
        glass: "border-border/40 bg-surface/70 backdrop-blur-sm",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

interface CardProps extends VariantProps<typeof cardVariants> {
  title: string;
  titleSize?: "sm" | "md" | "lg";
  description?: string;
  className?: string;
  headerClassName?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  accent?: "primary" | "success" | "warning" | "danger" | "info";
  noPadding?: boolean;
}

const ACCENT_BAR: Record<NonNullable<CardProps["accent"]>, string> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

const TITLE_SIZE: Record<NonNullable<CardProps["titleSize"]>, string> = {
  sm: "text-sm font-semibold",
  md: "text-base font-semibold",
  lg: "text-xl font-semibold",
};

export function Card({
  title,
  titleSize = "lg",
  description,
  className,
  headerClassName,
  actions,
  children,
  variant,
  accent,
  noPadding = false,
}: CardProps): JSX.Element {
  const titleId = React.useId();

  return (
    <section
      aria-labelledby={titleId}
      className={cn(cardVariants({ variant }), className)}
    >
      {accent && (
        <div className={cn("h-0.5 w-full rounded-t-xl", ACCENT_BAR[accent])} />
      )}
      <div className={cn(noPadding ? "" : "p-5")}>
        <div className={cn("flex items-start justify-between gap-3", headerClassName)}>
          <div className="min-w-0 flex-1">
            <h2
              className={cn("leading-tight tracking-tight text-foreground", TITLE_SIZE[titleSize])}
              id={titleId}
            >
              {title}
            </h2>
            {description && (
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && (
            <div className="flex shrink-0 items-center gap-2">{actions}</div>
          )}
        </div>
        <div className="mt-4 text-sm leading-relaxed">{children}</div>
      </div>
    </section>
  );
}
