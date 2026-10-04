"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Building2, ShoppingBag, ShieldCheck } from "lucide-react";
import { useWorkspace } from "@/features/providers";
import { demoUsers } from "@/services/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Choice } from "@/components/ui-kit";
import type { Operation } from "@/types/domain";
import { LiveLogin } from "./live-login";
export function Login() {
  const { login, dataMode } = useWorkspace();
  const router = useRouter();
  const [account, setAccount] = useState("up-admin");
  if (dataMode === "live") return <LiveLogin />;
  return (
    <main id="main" className="auth-screen">
      <div className="auth-intro">
        <div className="brand">
          <div className="brand-mark">UP</div>
          <div>
            <div className="brand-name">UP Data Intelligence</div>
            <div className="brand-sub">INTELIGÊNCIA QUE CONECTA</div>
          </div>
        </div>
        <span className="eyebrow">Moda. Dados. Decisões.</span>
        <h1>
          Uma visão completa.
          <br />
          Um novo nível de <em className="hl hl--up">inteligência.</em>
        </h1>
        <p className="lede">
          A inteligência da sua marca, em um ambiente operado pela UP.
        </p>
        <div className="auth-proof">
          <span>
            <Building2 />
            Sua marca
          </span>
          <span>
            <ShoppingBag />
            B2B & B2C
          </span>
          <span>
            <ShieldCheck />
            Acesso vinculado
          </span>
        </div>
      </div>
      <Card className="glass card login-card">
        <span className="eyebrow">Seu acesso</span>
        <h2>Bem-vindo à UP.</h2>
        <p className="muted">
          Escolha uma identidade demonstrativa para explorar seu acesso.
        </p>
        <Choice
          label="Usuário demonstrativo"
          value={account}
          onChange={setAccount}
          options={demoUsers.map((u) => ({
            value: u.id,
            label: u.role === "ADMIN" ? "Admin UP" : `${u.name} · ${u.email}`,
          }))}
        />
        <Button
          className="btn login-button"
          onClick={() => {
            login(account);
            router.replace("/");
          }}
        >
          Entrar <ArrowRight size={16} />
        </Button>
        <p className="metric-hint">
          Autenticação demonstrativa. Sem senhas reais. Cada usuário cliente
          está vinculado a uma única marca.
        </p>
      </Card>
    </main>
  );
}
export function OperationPicker({ required }: { required?: Operation }) {
  const { session, select, logout, tenants } = useWorkspace();
  const router = useRouter();
  if (!session) return null;
  return (
    <main id="main" className="workspace-screen">
      <div className="brand">
        <div className="brand-mark">UP</div>
        <div className="brand-name">UP Data Intelligence</div>
      </div>
      <span className="eyebrow">{session.name}</span>
      <h1>
        Escolha sua <em className="hl hl--up">operação.</em>
      </h1>
      {tenants.map((t) => (
        <section key={t.id} className="workspace-company">
          <div className="workspace-grid">
            {t.brands.map((b) => (
              <Card className="glass card" key={b.id}>
                <h3>{b.name}</h3>
                <div className="flex gap-2">
                  {b.operations
                    .filter((o) => !required || required === o.type)
                    .map((o) => (
                      <Button
                        className="btn btn--glass"
                        key={o.id}
                        onClick={() => {
                          select({
                            tenant_id: t.id,
                            store_id: o.id,
                            operation: o.type,
                          });
                          router.replace("/" + o.type.toLowerCase());
                        }}
                      >
                        {o.type}
                        <ArrowRight size={14} />
                      </Button>
                    ))}
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      <Button variant="ghost" onClick={logout}>
        Sair
      </Button>
    </main>
  );
}
