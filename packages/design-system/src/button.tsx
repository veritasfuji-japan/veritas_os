import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "./utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium",
    "transition-all duration-150 ease-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ds-color-focus-ring))] focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-40",
    "select-none",
  ].join(" "),
  {
    variants: {
      variant: {
        default: [
          "bg-primary text-primary-foreground shadow-sm",
          "hover:brightness-110 active:brightness-95 active:scale-[0.98]",
        ].join(" "),
        outline: [
          "border border-border bg-background text-foreground shadow-xs",
          "hover:bg-muted hover:border-border/80 active:scale-[0.98]",
        ].join(" "),
        ghost: [
          "bg-transparent text-foreground",
          "hover:bg-muted active:bg-muted/80",
        ].join(" "),
        subtle: [
          "bg-primary/10 text-primary border border-primary/20",
          "hover:bg-primary/15 active:bg-primary/20 active:scale-[0.98]",
        ].join(" "),
        danger: [
          "bg-danger text-danger-foreground shadow-sm",
          "hover:brightness-110 active:brightness-95 active:scale-[0.98]",
        ].join(" "),
        "danger-outline": [
          "border border-danger/50 bg-background text-danger",
          "hover:bg-danger/8 active:scale-[0.98]",
        ].join(" "),
        success: [
          "bg-success text-success-foreground shadow-sm",
          "hover:brightness-110 active:brightness-95 active:scale-[0.98]",
        ].join(" "),
        link: [
          "text-primary underline-offset-4",
          "hover:underline",
        ].join(" "),
      },
      size: {
        xs: "h-6 px-2 text-xs rounded-md",
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4 text-sm",
        lg: "h-10 px-5 text-sm",
        xl: "h-11 px-6 text-base",
        icon: "h-8 w-8 p-0",
        "icon-sm": "h-6 w-6 p-0 rounded-md",
        "icon-lg": "h-10 w-10 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, type = "button", variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading}
      {...props}
    >
      {loading && (
        <svg
          className="h-3.5 w-3.5 animate-spin"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  )
);

Button.displayName = "Button";
