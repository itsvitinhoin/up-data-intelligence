"use client";
import {
  createContext,
  useContext,
  useState,
  type ReactNode,
  type Dispatch,
  type SetStateAction,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import type {
  DashboardDataMode,
  Filters,
  Scope,
  Session,
} from "@/types/domain";
import type { ReadMetadata } from "@/services/api/http";
import { defaultFilters } from "@/config/tenants";
import { authorizedTenants, sessionFor } from "@/services/api";
export type OverviewReadState = {
  scopeKey: string;
  source: "demo" | "real" | "loading" | "error";
  metadata?: ReadMetadata;
};
export function overviewScopeKey(scope: Scope) {
  return `${scope.tenant_id}/${scope.store_id}/${scope.operation}`;
}
interface Workspace {
  session: Session | null;
  scope: Scope | null;
  filters: Filters;
  dataMode: DashboardDataMode;
  overviewReadState: OverviewReadState | null;
  setOverviewReadState: Dispatch<SetStateAction<OverviewReadState | null>>;
  login: (id: string) => void;
  logout: () => void;
  select: (scope: Scope) => void;
  setFilters: (filters: Filters) => void;
  refreshAccess: () => void;
}
const Context = createContext<Workspace | null>(null);
export function Providers({
  children,
  dataMode = "demo",
}: {
  children: ReactNode;
  dataMode?: DashboardDataMode;
}) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30000, retry: 1, refetchOnWindowFocus: false },
        },
      }),
  );
  const [session, setSession] = useState<Session | null>(null);
  const [scope, setScope] = useState<Scope | null>(null);
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [overviewReadState, setOverviewReadState] =
    useState<OverviewReadState | null>(null);
  function clear() {
    void client.cancelQueries();
    client.clear();
    setOverviewReadState(null);
  }
  return (
    <QueryClientProvider client={client}>
      <MotionConfig reducedMotion="user">
        <Context.Provider
          value={{
            session,
            scope,
            filters,
            dataMode,
            overviewReadState,
            setOverviewReadState,
            setFilters,
            login: (id) => {
              clear();
              const next = sessionFor(id);
              setSession(next);
              const choices = authorizedTenants(next).flatMap((t) =>
                t.brands.flatMap((b) =>
                  b.operations.map((o) => ({
                    tenant_id: t.id,
                    store_id: o.id,
                    operation: o.type,
                  })),
                ),
              );
              setScope(
                next.role !== "ADMIN" && choices.length === 1
                  ? choices[0]
                  : null,
              );
              setFilters(defaultFilters);
            },
            logout: () => {
              clear();
              setSession(null);
              setScope(null);
              setFilters(defaultFilters);
            },
            refreshAccess: () => {
              if (session) setSession(sessionFor(session.id));
              clear();
            },
            select: (next) => {
              if (
                !session ||
                !authorizedTenants(session).some(
                  (t) =>
                    t.id === next.tenant_id &&
                    t.brands.some((b) =>
                      b.operations.some(
                        (o) =>
                          o.id === next.store_id && o.type === next.operation,
                      ),
                    ),
                )
              )
                return;
              clear();
              setScope(next);
              setFilters(defaultFilters);
            },
          }}
        >
          {children}
        </Context.Provider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
export function useWorkspace() {
  const c = useContext(Context);
  if (!c) throw new Error("Workspace required");
  return c;
}
