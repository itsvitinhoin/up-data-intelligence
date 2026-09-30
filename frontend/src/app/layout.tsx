import type { Metadata } from "next";
import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/playfair-display/400-italic.css";
import "@fontsource/jetbrains-mono/400.css";
import "./globals.css";
import { Providers } from "@/features/providers";
export const metadata: Metadata = {
  title: {
    default: "UP Data Intelligence",
    template: "%s · UP Data Intelligence",
  },
  description:
    "Inteligência comercial para marcas de moda. Ambiente demonstrativo.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className="dark">
      <body>
        <a href="#main" className="skip-link">
          Ir para conteúdo
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
