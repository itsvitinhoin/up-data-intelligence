"use client";
import { Access } from "@/components/shell";
export function Application({ children }: { children: React.ReactNode }) {
  return <Access>{children}</Access>;
}
