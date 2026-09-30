"use client";
import { PageExport, ListExport, PrintContext } from "@/components/exports";
import { useState } from "react";
import { LogoUpload } from "@/components/logo-upload";
import { platforms, erps } from "@/types/domain";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plug, Users, LogOut, Plus } from "lucide-react";
import { useWorkspace } from "@/features/providers";
import { adminApi } from "@/services/api";
import { BrandIntegrationsPage } from "@/features/brand-integrations";
import {
  PageHead,
  Panel,
  Notice,
  Loading,
  Failure,
  Choice,
} from "@/components/ui-kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { Company, User } from "@/types/domain";
function useAdmin() {
  const { session, refreshAccess } = useWorkspace();
  if (!session) throw new Error("UP login required");
  const client = useQueryClient();
  return {
    session,
    changed: () => {
      refreshAccess();
      void client.invalidateQueries({ queryKey: ["up-admin"] });
    },
  };
}
function Field({
  name,
  label,
  type = "text",
  required = true,
}: {
  name: string;
  label: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <div className="form-field">
      <Label htmlFor={name}>{label}</Label>
      <Input
        id={name}
        name={name}
        type={type}
        required={required}
        autoComplete="off"
      />
    </div>
  );
}
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { logout } = useWorkspace();
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">UP</div>
          <div>
            <div className="brand-name">UP Admin</div>
            <div className="brand-sub">Operação da agência</div>
          </div>
        </div>
        <nav className="nav" aria-label="Administração UP">
          <Link className="nav-item" href="/admin">
            <Plug />
            Marcas
          </Link>
          <Link className="nav-item" href="/admin/users">
            <Users />
            Usuários e permissões
          </Link>
        </nav>
        <Button className="btn btn--glass mt-auto" onClick={logout}>
          <LogOut size={16} />
          Sair
        </Button>
      </aside>
      <main id="main" className="main">
        <PrintContext />
        <div className="topbar">
          <PageExport />
          <span className="eyebrow">UP Admin · gestão de marcas</span>
          <span className="spacer" />
          <span className="badge">Ambiente demonstrativo</span>
          <Button variant="ghost" onClick={logout}>
            Sair
          </Button>
        </div>
        <nav className="admin-mobile-nav" aria-label="Administração mobile">
          <Link href="/admin">Marcas</Link>
          <Link href="/admin/users">Usuários</Link>
        </nav>
        {children}
      </main>
    </div>
  );
}
export function CompaniesPage() {
  const { session, changed } = useAdmin();
  const meta = useQuery({
    queryKey: ["up-admin", "meta"],
    queryFn: () => adminApi.meta(session),
  });
  const [open, setOpen] = useState(false);
  const [operation, setOperation] = useState<Company["operation"]>("Ambos");
  const [account, setAccount] = useState("none");
  const [platform, setPlatform] = useState("none");
  const [erp, setErp] = useState("none");
  const [logo, setLogo] = useState("");
  const [logoBusy, setLogoBusy] = useState(false);
  const save = useMutation({
    mutationFn: (brand: Company) => adminApi.saveBrand(brand, session),
    onSuccess: () => {
      changed();
      setOpen(false);
      setLogo("");
    },
  });
  return (
    <BrandIntegrationsPage
      createAction={
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button className="btn">
              <Plus /> Criar marca
            </Button>
          </DialogTrigger>
          <DialogContent className="glass">
            <DialogTitle>Cadastrar marca</DialogTitle>
            <DialogDescription>
              Cadastro demonstrativo em memória. Use dados fictícios.
            </DialogDescription>
            <form
              className="form-grid"
              onSubmit={(event) => {
                event.preventDefault();
                const form = new FormData(event.currentTarget);
                save.mutate({
                  id: crypto.randomUUID(),
                  name: String(form.get("name")).trim(),
                  cnpj: String(form.get("cnpj")),
                  logo,
                  platform:
                    platform === "none"
                      ? null
                      : (platform as Company["platform"]),
                  erp: erp === "none" ? null : (erp as Company["erp"]),
                  segment: String(form.get("segment")),
                  operation,
                  status: "ACTIVE",
                  meta_account_id: account === "none" ? null : account,
                });
              }}
            >
              <Field name="name" label="Nome da marca" />
              <Field name="cnpj" label="CNPJ" />
              <LogoUpload
                value={logo}
                onChange={setLogo}
                onBusy={setLogoBusy}
              />
              <Choice
                label="Plataforma"
                value={platform}
                onChange={setPlatform}
                options={[
                  { value: "none", label: "Não informado" },
                  ...platforms.map((value) => ({ value, label: value })),
                ]}
              />
              <Choice
                label="ERP"
                value={erp}
                onChange={setErp}
                options={[
                  { value: "none", label: "Não informado" },
                  ...erps.map((value) => ({ value, label: value })),
                ]}
              />
              <Field name="segment" label="Segmento" />
              <Choice
                label="Operação"
                value={operation}
                onChange={(value) =>
                  setOperation(value as Company["operation"])
                }
                options={["B2B", "B2C", "Ambos"].map((value) => ({
                  value,
                  label: value,
                }))}
              />
              <Choice
                label="Conta Meta Ads vinculada"
                value={account}
                onChange={setAccount}
                options={[
                  { value: "none", label: "Vincular depois" },
                  ...(meta.data?.accounts
                    .filter((item) => item.status === "AVAILABLE")
                    .map((item) => ({
                      value: item.meta_account_id,
                      label: item.account_name,
                    })) ?? []),
                ]}
              />
              {save.isError && <p role="alert">{save.error.message}</p>}
              <Button
                className="btn"
                type="submit"
                disabled={save.isPending || logoBusy}
              >
                Salvar marca
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      }
    />
  );
}
export function UsersPage() {
  const { session, changed } = useAdmin();
  const q = useQuery({
    queryKey: ["up-admin", "users"],
    queryFn: () => adminApi.users(session),
  });
  const brands = useQuery({
    queryKey: ["up-admin", "brands"],
    queryFn: () => adminApi.brands(session),
  });
  const [open, setOpen] = useState(false);
  const [brand, setBrand] = useState("demo-mx");
  const [role, setRole] = useState<"VIEWER" | "MANAGER">("VIEWER");
  const save = useMutation({
    mutationFn: (u: User) => adminApi.saveUser(u, session),
    onSuccess: () => {
      changed();
      setOpen(false);
    },
  });
  return (
    <>
      <PageHead
        eyebrow="UP Admin · Acessos"
        title={
          <>
            Usuários de cada <em className="hl hl--up">marca.</em>
          </>
        }
        description="A UP cria e gerencia o acesso. Usuários clientes não veem outras marcas."
        action={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="btn">
                <Plus />
                Criar usuário
              </Button>
            </DialogTrigger>
            <DialogContent className="glass">
              <DialogTitle>Usuário vinculado à marca</DialogTitle>
              <DialogDescription>
                Acesso demonstrativo disponível no login após salvar. Não envia
                convite.
              </DialogDescription>
              <form
                className="form-grid"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  save.mutate({
                    id: crypto.randomUUID(),
                    name: String(f.get("user-name")).trim(),
                    email: String(f.get("email")).trim(),
                    phone: String(f.get("phone")),
                    role,
                    brand_id: brand,
                  });
                }}
              >
                <Field name="user-name" label="Nome" />
                <Field name="email" label="Email fictício" type="email" />
                <Field
                  name="phone"
                  label="Telefone fictício"
                  required={false}
                />
                <div className="form-field">
                  <Label htmlFor="password">Senha</Label>
                  <Input
                    id="password"
                    type="password"
                    disabled
                    placeholder="Definição segura pelo serviço de autenticação futuro"
                  />
                </div>
                <Choice
                  label="Marca vinculada"
                  value={brand}
                  onChange={setBrand}
                  options={
                    brands.data?.map((b) => ({ value: b.id, label: b.name })) ??
                    []
                  }
                />
                <Choice
                  label="Permissão"
                  value={role}
                  onChange={(v) => setRole(v as typeof role)}
                  options={[
                    { value: "VIEWER", label: "Visualização" },
                    {
                      value: "MANAGER",
                      label: "Gestão comercial · leitura nesta etapa",
                    },
                  ]}
                />
                {save.isError && <p role="alert">{save.error.message}</p>}
                <Button type="submit" className="btn" disabled={save.isPending}>
                  Salvar usuário
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        }
      />
      {q.isPending ? (
        <Loading />
      ) : q.isError ? (
        <Failure retry={() => void q.refetch()} />
      ) : (
        <Panel
          title="Acessos dos clientes"
          action={<ListExport rows={q.data} name="usuarios" />}
        >
          <div className="users-list">
            {q.data.map((u) => (
              <div key={u.id}>
                <span className="avatar">
                  <Users size={17} />
                </span>
                <strong>
                  {u.name}
                  <small className="block muted">
                    {u.email} · {u.phone || "Telefone não informado"}
                  </small>
                  <small className="block">
                    {brands.data?.find((b) => b.id === u.brand_id)?.name}
                  </small>
                </strong>
                <Choice
                  label={`Permissão de ${u.name}`}
                  value={u.role}
                  onChange={(role) =>
                    save.mutate({ ...u, role: role as User["role"] })
                  }
                  options={[
                    { value: "VIEWER", label: "Visualização" },
                    { value: "MANAGER", label: "Gestão comercial" },
                  ]}
                />
              </div>
            ))}
          </div>
        </Panel>
      )}
    </>
  );
}
export { BrandIntegrationsPage as IntegrationsPage } from "@/features/brand-integrations";
export function SettingsPage() {
  const { logout } = useWorkspace();
  return (
    <>
      <PageHead
        eyebrow="Acesso da marca"
        title="Sua sessão"
        description="Preferências internas e integrações são administradas pela UP."
      />
      <Notice>
        Ambiente demonstrativo. Autorização real precisa ser validada no
        servidor.
      </Notice>
      <Button className="btn" onClick={logout}>
        Sair
      </Button>
    </>
  );
}
