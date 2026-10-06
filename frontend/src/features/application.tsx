"use client";
import { ManagerBoundary } from "@/dashboard/engine";
import { Access } from "@/components/shell";
export function Application({ children }: { children: React.ReactNode }) {
  return (
    <Access>
      <ManagerBoundary>{children}</ManagerBoundary>
    </Access>
  );
}
