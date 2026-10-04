"use client";
import { useState } from "react";
import { SecureOnboardingForm } from "./secure-onboarding";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useRouter } from "next/navigation";
import { useWorkspace } from "./providers";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
export function LiveBrands() {
  const [message, setMessage] = useState("");
  const { tenants, select, logout, refreshAccess } = useWorkspace();
  const router = useRouter();
  return (
    <main className="workspace-screen">
      <span className="eyebrow">Admin UP</span>
      <h1>Marcas</h1>
      {message && <p role="status">{message}</p>}
      {tenants.map((t) => (
        <section key={t.id} className="workspace-company">
          <h2>{t.name}</h2>
          <Dialog>
            <DialogTrigger asChild>
              <Button className="btn btn--glass">Criar marca</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogTitle>Cadastrar marca</DialogTitle>
              <DialogDescription>
                Credenciais permanecem no backend. Nenhum token de mídia é
                armazenado no navegador.
              </DialogDescription>
              <SecureOnboardingForm
                tenant={t.id}
                onCreated={() => {
                  setMessage("Marca cadastrada. Acompanhe sua instalação.");
                  refreshAccess();
                }}
              />
            </DialogContent>
          </Dialog>
          <div className="workspace-grid">
            {t.brands.map((b) => (
              <Card key={b.id} className="glass card">
                <h3>{b.name}</h3>
                {b.operations.map((o) => (
                  <Button
                    className="btn btn--glass"
                    key={o.id}
                    onClick={() => {
                      select({
                        tenant_id: t.id,
                        workspace_operation_id: o.id,
                        store_id: o.id,
                        operation: o.type,
                      });
                      router.push("/" + o.type.toLowerCase());
                    }}
                  >
                    Ver Dashboard · {o.type}
                  </Button>
                ))}
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
