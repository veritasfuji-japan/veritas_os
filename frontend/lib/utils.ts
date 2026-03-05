import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Strip HTML tags and null bytes from untrusted text to prevent XSS.
 * React already escapes string interpolation, but this adds defence-in-depth
 * for content originating from external APIs.
 */
export function sanitizeText(value: unknown): string {
  if (typeof value !== "string") return String(value ?? "");
  return value.replace(/<[^>]*>/g, "").replace(/\0/g, "");
}
