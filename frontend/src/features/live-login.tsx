"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Building2, ShoppingBag, ShieldCheck, ArrowRight } from "lucide-react";
import { firstAccess, liveSignIn, resetPassword } from "@/services/auth/client";
import { useWorkspace } from "./providers";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
export function LiveLogin() {
  const [mode, setMode] = useState<"login" | "first" | "reset">("login");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const { refreshAccess } = useWorkspace();
  const router = useRouter();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      const email = String(fields.get("email") ?? ""),
        password = String(fields.get("password") ?? "");
      if (mode === "first") {
        await firstAccess(email, password);
        setMessage(
          "Verifique seu e-mail. A criação da conta não concede acesso à plataforma.",
        );
      } else if (mode === "reset") {
        await resetPassword(email);
        setMessage(
          "Se houver uma conta válida, enviaremos as instruções para seu e-mail.",
        );
      } else {
        await liveSignIn(email, password);
        refreshAccess();
        router.replace("/");
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : "";
      setMessage(
        reason === "verified_email_required"
          ? "Verifique seu e-mail antes de entrar."
          : reason === "access_not_provisioned"
            ? "Acesso ainda não provisionado pela UP."
            : "Não foi possível concluir. Verifique seus dados e tente novamente.",
      );
    } finally {
      setBusy(false);
    }
  }
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
        <h2>
          {mode === "first"
            ? "Primeiro acesso"
            : mode === "reset"
              ? "Esqueci minha senha"
              : "Bem-vindo à UP."}
        </h2>
        <p className="muted">
          Ambiente DEV interno. Entre com seu acesso autorizado.
        </p>
        <form className="form-grid" onSubmit={submit}>
          <label htmlFor="live-email">E-mail</label>
          <Input
            id="live-email"
            name="email"
            type="email"
            autoComplete="email"
            required
          />
          {mode !== "reset" && (
            <>
              <label htmlFor="live-password">Senha</label>
              <Input
                id="live-password"
                name="password"
                type="password"
                minLength={mode === "first" ? 12 : 6}
                autoComplete={
                  mode === "first" ? "new-password" : "current-password"
                }
                required
              />
            </>
          )}
          <Button className="btn login-button" disabled={busy} type="submit">
            {busy
              ? "Aguarde…"
              : mode === "first"
                ? "Criar conta"
                : mode === "reset"
                  ? "Enviar instruções"
                  : "Entrar"}
            <ArrowRight size={16} />
          </Button>
        </form>
        {message && <p role="status">{message}</p>}
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setMode("login")}>
            Entrar
          </Button>
          <Button variant="ghost" onClick={() => setMode("first")}>
            Primeiro acesso
          </Button>
          <Button variant="ghost" onClick={() => setMode("reset")}>
            Esqueci minha senha
          </Button>
        </div>
      </Card>
    </main>
  );
}
