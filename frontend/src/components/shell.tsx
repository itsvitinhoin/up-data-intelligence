"use client";
import { InstallationBoundary } from "@/components/installation-state";
import { PageExport, PrintContext } from "@/components/exports";
import { PeriodFilter } from "@/components/period-filter";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Menu,
  ChevronDown,
  ChevronRight,
  Search,
  LogOut,
  Bell,
  ArrowUpRight,
  Plug,
  UserCog,
} from "lucide-react";
import { navigation } from "@/config/navigation";
import { defaultFilters } from "@/config/tenants";
import {
  dashboardSourceLabel,
  activePageState,
  isB2BReadPage,
} from "@/lib/dashboard-source";
import { useWorkspace } from "@/features/providers";
import { useResource } from "@/hooks/use-resource";
import { useQuery } from "@tanstack/react-query";
import { decodeReadEnvelope } from "@/services/api/http";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import { Choice, Empty } from "@/components/ui-kit";
import { Login, OperationPicker } from "@/features/auth";
import { AdminShell, CompaniesPage } from "@/features/admin";
function Redirect({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to);
  }, [router, to]);
  return null;
}
export function Access({ children }: { children: React.ReactNode }) {
  const { session, scope, dataMode, tenants, sessionLoading, sessionError } =
    useWorkspace();
  const pathname = usePathname();
  if (sessionLoading)
    return <main className="workspace-screen">Conectando sua sessão…</main>;
  if (!session)
    return (
      <>
        <Login />
        {sessionError && <p role="alert">{sessionError}</p>}
      </>
    );
  if (pathname === "/" || pathname === "/login") {
    if (session.role === "ADMIN") return <Redirect to="/admin" />;
    if (!scope) return <OperationPicker />;
    return <Redirect to={"/" + scope.operation.toLowerCase()} />;
  }
  if (pathname.startsWith("/admin")) {
    if (session.role !== "ADMIN")
      return (
        <main className="workspace-screen">
          <h1>Acesso restrito</h1>
          <p>Área exclusiva da UP.</p>
          <Link href="/">Voltar à sua marca</Link>
        </main>
      );
    return (
      <AdminShell>
        {pathname === "/admin" ? (
          <CompaniesPage />
        ) : dataMode === "live" ? (
          <section className="card glass">
            <h1>Indisponível</h1>
            <p>
              Gestão de usuários ainda não conectada. Permissões reais são
              administradas pelo backend.
            </p>
          </section>
        ) : (
          children
        )}
      </AdminShell>
    );
  }
  if (!scope)
    return session.role === "ADMIN" ? (
      <Redirect to="/admin" />
    ) : (
      <OperationPicker />
    );
  if (pathname === "/settings" && session.role !== "ADMIN")
    return <Redirect to={"/" + scope.operation.toLowerCase()} />;
  const required = pathname.startsWith("/b2b")
    ? "B2B"
    : pathname.startsWith("/b2c")
      ? "B2C"
      : undefined;
  if (required && scope.operation !== required) {
    const available = tenants.some((t) =>
      t.brands.some((b) => b.operations.some((o) => o.type === required)),
    );
    return available ? (
      <OperationPicker required={required} />
    ) : (
      <Redirect to={"/" + scope.operation.toLowerCase()} />
    );
  }
  if (
    dataMode === "live" &&
    (scope.operation !== "B2B" || !isB2BReadPage(pathname))
  )
    return (
      <Shell>
        <main className="workspace-screen">
          <h1>Indisponível</h1>
          <p>Cobertura ainda não certificada</p>
        </main>
      </Shell>
    );
  return <Shell>{children}</Shell>;
}
function Navigation({ close }: { close?: () => void }) {
  const path = usePathname();
  const { scope, session, select, tenants } = useWorkspace();
  const [expanded, setExpanded] = useState<string[]>([
    ...(path.startsWith("/erp") ? ["ERP"] : []),
    ...(path.startsWith("/campaigns") ? ["Campanhas"] : []),
  ]);
  const tenant = tenants.find((t) => t.id === scope?.tenant_id);
  const brand = tenant?.brands.find((b) =>
    b.operations.some((o) => o.id === scope?.store_id),
  );
  function follow(href: string) {
    const target = href.startsWith("/b2c")
      ? "B2C"
      : href.startsWith("/b2b")
        ? "B2B"
        : null;
    if (target && target !== scope?.operation) {
      const op = brand?.operations.find((o) => o.type === target);
      if (op && scope)
        select({ ...scope, store_id: op.id, operation: op.type });
    }
    close?.();
  }
  return (
    <>
      <div className="brand">
        <div className="brand-mark">UP</div>
        <div>
          <div className="brand-name">UP Data Intelligence</div>
          <div className="brand-sub">Inteligência comercial</div>
        </div>
      </div>
      <nav className="nav" aria-label="Principal">
        <div>
          <div className="nav-label">Workspace</div>
          <ul>
            {navigation
              .filter(
                (item) =>
                  (item.label !== "Configurações" ||
                    session?.role === "ADMIN") &&
                  (!item.operation ||
                    (scope?.operation === item.operation &&
                      brand?.operations.some(
                        (o) => o.type === item.operation,
                      ))),
              )
              .map((item) => (
                <li key={item.href}>
                  {item.children ? (
                    <>
                      <button
                        className="nav-item"
                        aria-expanded={expanded.includes(item.label)}
                        onClick={() =>
                          setExpanded((e) =>
                            e.includes(item.label)
                              ? e.filter((v) => v !== item.label)
                              : [...e, item.label],
                          )
                        }
                      >
                        <item.icon />
                        <span className="grow">{item.label}</span>
                        <ChevronDown className="chev" />
                      </button>
                      <div
                        className="nav-sub"
                        hidden={!expanded.includes(item.label)}
                      >
                        <ul>
                          {item.children.map(([label, href]) => (
                            <li key={href}>
                              <Link
                                href={href}
                                onClick={() => follow(href)}
                                aria-current={
                                  path === href ? "page" : undefined
                                }
                              >
                                {label}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </>
                  ) : (
                    <Link
                      className="nav-item"
                      href={item.href}
                      onClick={() => follow(item.href)}
                      aria-current={path === item.href ? "page" : undefined}
                    >
                      <item.icon />
                      <span className="grow">{item.label}</span>
                    </Link>
                  )}
                </li>
              ))}
          </ul>
        </div>
        {session?.role === "ADMIN" && (
          <div>
            <div className="nav-label">Administração</div>
            <ul>
              {[
                ["Marcas", "/admin", Plug],
                ["Usuários", "/admin/users", UserCog],
              ].map(([label, href, Icon]) => (
                <li key={String(href)}>
                  <Link
                    className="nav-item"
                    href={String(href)}
                    onClick={close}
                    aria-current={path === href ? "page" : undefined}
                  >
                    {typeof Icon !== "string" && <Icon />}
                    {String(label)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </nav>
    </>
  );
}
function SearchDialog() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const data = useResource("customers");
  const { dataMode, scope } = useWorkspace();
  const real = useQuery({
    queryKey: [
      "live-customer-search",
      scope?.tenant_id,
      scope?.workspace_operation_id,
      scope?.operation,
    ],
    enabled: dataMode === "live" && open && scope?.operation === "B2B",
    retry: false,
    queryFn: async ({ signal }) => {
      const params = new URLSearchParams({
        tenant_id: scope!.tenant_id,
        workspace_operation_id: scope!.workspace_operation_id!,
        operation: scope!.operation,
        page_size: "25",
      });
      const response = await fetch(`/api/dashboard/customers?${params}`, {
        cache: "no-store",
        signal,
      });
      if (!response.ok) throw new Error("customer_search_unavailable");
      return decodeReadEnvelope("customers", await response.json());
    },
  });
  const records =
    dataMode === "live"
      ? real.data?.data.map((c) => ({
          id: c.customer_id,
          name: c.name ?? "Nome não disponível",
          city: c.city,
          state: c.state,
        }))
      : data.data;
  const matches =
    records?.filter((c) => c.name.toLowerCase().includes(text.toLowerCase())) ??
    [];
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="search glass">
          <Search />
          <span>Buscar cliente...</span>
          <kbd>⌕</kbd>
        </button>
      </DialogTrigger>
      <DialogContent className="glass">
        <DialogTitle>Encontre um cliente</DialogTitle>
        <DialogDescription>
          {dataMode === "live"
            ? "Busca na página atual de até 25 clientes autorizados. A lista completa está em Clientes."
            : "Busca na operação selecionada."}
        </DialogDescription>
        <Input
          aria-label="Buscar cliente pelo nome"
          placeholder="Nome da empresa"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="search-results">
          {matches.map((c) => (
            <Link
              onClick={() => setOpen(false)}
              key={c.id}
              href={`/customers/${c.id}`}
            >
              <span>
                {c.name}
                <small>
                  {c.city} · {c.state}
                </small>
              </span>
              <ArrowUpRight size={16} />
            </Link>
          ))}
          {dataMode === "live" && real.isError ? (
            <p>Cobertura ainda não certificada</p>
          ) : (
            !matches.length && <Empty />
          )}
          {dataMode === "live" && (
            <Link href="/customers" onClick={() => setOpen(false)}>
              Abrir Clientes
            </Link>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
export function Shell({ children }: { children: React.ReactNode }) {
  const {
    session,
    scope,
    select,
    logout,
    dataMode,
    dashboardPageState,
    tenants,
  } = useWorkspace();
  const router = useRouter();
  const path = usePathname();
  const [menu, setMenu] = useState(false);
  const [notifications, setNotifications] = useState(true);
  const options = tenants
    .filter((t) => session?.tenant_ids.includes(t.id))
    .flatMap((t) =>
      t.brands.flatMap((b) =>
        b.operations.map((o) => ({
          value: o.id,
          label: `${b.name} · ${o.type}`,
          tenant: t.id,
          operation: o.type,
        })),
      ),
    );
  const selected = options.find((o) => o.value === scope?.store_id);
  const overviewPreview =
    isB2BReadPage(path) && dataMode !== "demo" && scope?.operation === "B2B";
  const currentRead = activePageState(
    path,
    dataMode,
    scope,
    dashboardPageState,
  );
  const realOverview =
    currentRead?.source === "real" || currentRead?.source === "partial-real";
  const failedOverview = currentRead?.source === "error-real";
  const pendingOverview =
    overviewPreview && (!currentRead || currentRead.source === "loading-real");
  const sourceLabel = dashboardSourceLabel(
    path,
    dataMode,
    scope,
    dashboardPageState,
  );
  return (
    <div className="app">
      <aside className="sidebar">
        <Navigation />
        <div className="side-foot glass">
          <span className="avatar">UP</span>
          <div className="who">
            {session?.name}
            <small>
              {session?.role.toLowerCase()} ·{" "}
              {dataMode === "live" ? "Dados reais" : "Demo"}
            </small>
          </div>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Sair"
            onClick={logout}
          >
            <LogOut size={15} />
          </Button>
        </div>
      </aside>
      <main className="main" id="main">
        <PrintContext />
        <div className="topbar">
          <Sheet open={menu} onOpenChange={setMenu}>
            <SheetTrigger asChild>
              <Button
                className="icon-btn menu-btn"
                aria-label="Abrir navegação"
              >
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="mobile-navigation">
              <SheetTitle className="sr-only">Navegação</SheetTitle>
              <SheetDescription className="sr-only">
                Módulos disponíveis para a operação selecionada.
              </SheetDescription>
              <Navigation close={() => setMenu(false)} />
            </SheetContent>
          </Sheet>
          <div className="crumbs">
            Workspace <ChevronRight size={13} />
            <b>{scope?.operation}</b>
          </div>
          <div className="spacer" />
          {dataMode === "read-api-preview" &&
          overviewPreview &&
          currentRead?.source !== "demo" ? (
            <button
              className="search glass"
              disabled
              title="Busca de clientes indisponível neste preview"
            >
              <Search />
              <span>Busca indisponível neste preview</span>
            </button>
          ) : (
            <SearchDialog />
          )}
          {path !== "/b2c/stock" &&
            !(
              overviewPreview &&
              currentRead?.source !== "demo" &&
              /^\/customers\/[^/]+$/.test(path)
            ) && <PeriodFilter />}
          <PageExport />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Encerrar sessão"
            onClick={logout}
          >
            <LogOut size={15} />
          </Button>
          <Choice
            label={
              session?.role === "ADMIN"
                ? "Marca e operação"
                : "Operação da marca"
            }
            value={scope?.store_id ?? ""}
            options={options}
            onChange={(id) => {
              const o = options.find((x) => x.value === id);
              if (o) {
                select({
                  tenant_id: o.tenant,
                  store_id: o.value,
                  operation: o.operation,
                });
                router.push("/" + o.operation.toLowerCase());
              }
            }}
          />
          {(!overviewPreview || currentRead?.source === "demo") && (
            <Dialog>
              <DialogTrigger asChild>
                <Button
                  variant="ghost"
                  className="icon-btn"
                  aria-label="Notificações"
                >
                  <Bell />
                  {notifications && <span className="notification-dot" />}
                </Button>
              </DialogTrigger>
              <DialogContent className="glass">
                <DialogTitle>Seu workspace</DialogTitle>
                <DialogDescription>
                  Notificações demonstrativas.
                </DialogDescription>
                {notifications ? (
                  <>
                    <p>
                      Seu ambiente de demonstração está pronto para explorar.
                    </p>
                    <Button
                      onClick={() => setNotifications(false)}
                      className="btn"
                    >
                      Marcar como lida
                    </Button>
                  </>
                ) : (
                  <Empty
                    title="Tudo em dia"
                    description="Você não tem notificações pendentes."
                  />
                )}
              </DialogContent>
            </Dialog>
          )}
        </div>
        <div className="workspace-strip">
          <span>
            {selected?.label}{" "}
            <span className="muted">
              /{" "}
              {path.startsWith("/admin")
                ? "Administração"
                : "Inteligência comercial"}
            </span>
          </span>
          <span className="badge badge--up">{sourceLabel}</span>
        </div>
        <InstallationBoundary>{children}</InstallationBoundary>
        <footer className="note">
          {realOverview
            ? `UP Data Intelligence · Dados reais · Analytics V1${currentRead?.metadata?.history_complete ? "" : " · Histórico parcial"}`
            : failedOverview
              ? "UP Data Intelligence · Falha na leitura real · Nenhum dado demonstrativo foi usado nesta página"
              : currentRead?.source === "unavailable-real"
                ? "UP Data Intelligence · Cobertura indisponível · Nenhum dado demonstrativo foi usado nesta página"
                : pendingOverview
                  ? "UP Data Intelligence · Aguardando publicação Analytics V1"
                  : "UP Data Intelligence · Ambiente demonstrativo · Nenhuma integração real conectada"}
        </footer>
      </main>
    </div>
  );
}
export function FiltersBar({ showChannel = true }: { showChannel?: boolean }) {
  const { filters, setFilters } = useWorkspace();
  return (
    <section className="filters glass" aria-label="Filtros globais">
      {showChannel && (
        <Choice
          label="Canal"
          value={filters.channel}
          onChange={(channel) => setFilters({ ...filters, channel })}
          options={[
            { value: "all", label: "Todos os canais" },
            { value: "meta", label: "Meta Ads" },
            { value: "google", label: "Google Ads" },
          ]}
        />
      )}
      <Choice
        label="Coleção"
        value={filters.collection}
        onChange={(collection) => setFilters({ ...filters, collection })}
        options={[
          { value: "all", label: "Todas as coleções" },
          { value: "primavera", label: "Primavera 26" },
          { value: "verao", label: "Alto Verão 27" },
        ]}
      />
      <div className="push">
        <Button
          variant="ghost"
          className="btn-ghost"
          onClick={() => setFilters(defaultFilters)}
        >
          Limpar filtros
        </Button>
      </div>
    </section>
  );
}
