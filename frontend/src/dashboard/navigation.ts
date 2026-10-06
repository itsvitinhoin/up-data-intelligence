import {
  LayoutDashboard,
  Database,
  TrendingUp,
  ShoppingBag,
  MessageCircle,
  Users,
  Package,
  ReceiptText,
} from "lucide-react";
import { managerPages } from "./registry";
export function managerNavigation(operation: "B2B" | "B2C") {
  const pages = managerPages.filter((page) =>
    page.path.startsWith(`/${operation.toLowerCase()}`),
  );
  const groups =
    operation === "B2B"
      ? ["Visão Geral", "ERP", "Performance", "Ecommerce", "WhatsApp"]
      : ["Visão Geral", "Pedidos", "Clientes", "Produtos", "Performance"];
  const icons = {
    "Visão Geral": LayoutDashboard,
    ERP: Database,
    Performance: TrendingUp,
    Ecommerce: ShoppingBag,
    WhatsApp: MessageCircle,
    Clientes: Users,
    Produtos: Package,
    Pedidos: ReceiptText,
  };
  return groups.map((group) => {
    const matches = pages.filter((page) => page.group === group);
    return {
      label: group,
      href: matches[0]?.path ?? "/",
      icon: icons[group as keyof typeof icons],
      operation,
      children:
        matches.length > 1
          ? matches.map((page) => [page.title, page.path])
          : undefined,
    };
  });
}
