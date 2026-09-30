"use client";
export default function ErrorPage({
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <main id="main" className="auth-screen">
      <section className="glass card" role="alert">
        <h1>Algo interrompeu a visualização.</h1>
        <p>Seus dados não foram alterados.</p>
        <button className="btn" onClick={reset}>
          Tentar novamente
        </button>
      </section>
    </main>
  );
}
