"use client";
import {
  createContext,
  useEffect,
  useCallback,
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
  Tenant,
} from "@/types/domain";
import type { DashboardPageState } from "@/lib/dashboard-source";
import type { InstallationCoverage } from "@/types/installation";
import { exclusiveToInclusive } from "@/lib/period";
import { defaultFilters } from "@/config/tenants";
import { authorizedTenants, sessionFor } from "@/services/api";
import { parseCatalog, catalogView } from "@/services/auth/catalog";
import { liveSignOut } from "@/services/auth/client";
export function overviewScopeKey(scope: Scope) {
  return `${scope.tenant_id}/${scope.store_id}/${scope.operation}`;
}
interface Workspace {
  tenants: Tenant[];
  sessionLoading: boolean;
  sessionError: string | null;
  session: Session | null;
  onboardingEnabled: boolean;
  scope: Scope | null;
  filters: Filters;
  dataMode: DashboardDataMode;
  dashboardPageState: DashboardPageState | null;
  setDashboardPageState: Dispatch<SetStateAction<DashboardPageState | null>>;
  login: (id: string) => void;
  logout: () => void;
  select: (scope: Scope, window?: InstallationCoverage) => void;
  setFilters: (filters: Filters) => void;
  refreshAccess: () => void;
}
const Context = createContext<Workspace | null>(null);
export function Providers({
  children,
  dataMode = "demo",
  onboardingEnabled = false,
}: {
  children: ReactNode;
  dataMode?: DashboardDataMode;
  onboardingEnabled?: boolean;
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
  const [liveTenants, setLiveTenants] = useState<Tenant[]>([]);
  const [sessionLoading, setSessionLoading] = useState(dataMode === "live");
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [scope, setScope] = useState<Scope | null>(null);
  const installSession = useCallback(async (response: Response) => {
    try {
      if (!response.ok) {
        setSession(null);
        setLiveTenants([]);
        setSessionError(
          response.status === 401
            ? null
            : response.status === 403
              ? "Acesso ainda não provisionado."
              : "Sessão temporariamente indisponível.",
        );
        return;
      }
      const view = catalogView(parseCatalog(await response.json()));
      setSession(view.session);
      setLiveTenants(view.tenants);
      setSessionError(null);
      const choices = view.tenants.flatMap((t) =>
        t.brands.flatMap((b) =>
          b.operations.map((o) => ({
            tenant_id: t.id,
            workspace_operation_id: o.id,
            store_id: o.id,
            operation: o.type,
          })),
        ),
      );
      if (view.session.role !== "ADMIN" && choices.length === 1)
        setScope(choices[0]);
    } catch {
      setSession(null);
      setLiveTenants([]);
      setSessionError("Sessão temporariamente indisponível.");
    } finally {
      setSessionLoading(false);
    }
  }, []);
  const bootstrap = useCallback(
    () =>
      fetch("/api/session", { cache: "no-store", credentials: "same-origin" })
        .then(installSession)
        .catch(() => {
          setSession(null);
          setLiveTenants([]);
          setSessionLoading(false);
          setSessionError("Sessão temporariamente indisponível.");
        }),
    [installSession],
  );
  useEffect(() => {
    if (dataMode !== "live") return;
    const controller = new AbortController();
    void fetch("/api/session", {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(installSession)
      .catch(() => {
        if (!controller.signal.aborted) {
          setSession(null);
          setLiveTenants([]);
          setSessionLoading(false);
          setSessionError("Sessão temporariamente indisponível.");
        }
      });
    return () => controller.abort();
  }, [dataMode, installSession]);
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [dashboardPageState, setDashboardPageState] =
    useState<DashboardPageState | null>(null);
  function clear() {
    setDashboardPageState(null);
    void client.cancelQueries();
    client.clear();
  }
  return (
    <QueryClientProvider client={client}>
      <MotionConfig reducedMotion="user">
        <Context.Provider
          value={{
            session,
            tenants:
              dataMode === "live"
                ? liveTenants
                : session
                  ? authorizedTenants(session)
                  : [],
            sessionLoading,
            sessionError,
            onboardingEnabled,
            scope,
            filters,
            dataMode,
            dashboardPageState,
            setDashboardPageState,
            setFilters,
            login: (id) => {
              if (dataMode === "live") {
                void bootstrap();
                return;
              }
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
              if (dataMode === "live") {
                void liveSignOut()
                  .then(() => {
                    clear();
                    setSession(null);
                    setScope(null);
                    setLiveTenants([]);
                    setFilters(defaultFilters);
                  })
                  .catch(() =>
                    setSessionError("Não foi possível sair. Tente novamente."),
                  );
                return;
              }
              clear();
              setSession(null);
              setScope(null);
              setFilters(defaultFilters);
            },
            refreshAccess: () => {
              if (dataMode === "live") {
                clear();
                void bootstrap();
                return;
              }
              if (session) setSession(sessionFor(session.id));
              clear();
            },
            select: (next, window) => {
              if (
                !session ||
                !(
                  dataMode === "live" ? liveTenants : authorizedTenants(session)
                ).some(
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
              setScope(
                dataMode === "live"
                  ? {
                      ...next,
                      workspace_operation_id:
                        next.workspace_operation_id ?? next.store_id,
                    }
                  : next,
              );
              setFilters(
                window
                  ? {
                      ...defaultFilters,
                      period: "custom",
                      from: window.from,
                      to: exclusiveToInclusive(window.to),
                    }
                  : defaultFilters,
              );
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
