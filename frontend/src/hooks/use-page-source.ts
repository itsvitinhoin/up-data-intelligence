"use client";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useWorkspace, overviewScopeKey } from "@/features/providers";
import type { DashboardPageState } from "@/lib/dashboard-source";
import type { ReadMetadata } from "@/services/api/http";

export function usePageSource(
  source: DashboardPageState["source"],
  metadata?: ReadMetadata,
) {
  const { scope, setDashboardPageState } = useWorkspace();
  const path = usePathname(),
    scopeKey = scope ? overviewScopeKey(scope) : "";
  useEffect(() => {
    setDashboardPageState({ path, scopeKey, source, metadata });
  }, [path, scopeKey, source, metadata, setDashboardPageState]);
}
