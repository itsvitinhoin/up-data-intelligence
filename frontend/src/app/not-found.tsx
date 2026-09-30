import Link from "next/link";
export default function NotFound() {
  return (
    <main className="auth-screen" id="main">
      <section className="glass card">
        <span className="eyebrow">404</span>
        <h1>Não encontramos esta página.</h1>
        <Link className="btn" href="/">
          Voltar ao painel
        </Link>
      </section>
    </main>
  );
}
