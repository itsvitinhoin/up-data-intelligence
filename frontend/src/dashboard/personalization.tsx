"use client";
import { useRouter } from "next/navigation";
import { usePathname } from "next/navigation";
import { SlidersHorizontal, ArrowUp, ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Choice } from "@/components/ui-kit";
import { useWorkspace } from "@/features/providers";
import { managerPage, managerPages, WidgetRegistry } from "./registry";
import { useTemplate } from "./provider";
import { validatedPagePreference } from "./preferences";
export function Personalization() {
  const path = usePathname(),
    state = useTemplate(),
    { scope, session, dataMode, demoReview, reviewB2C, returnToLive } =
      useWorkspace();
  const router = useRouter();
  const page = managerPage(path),
    pref = validatedPagePreference(
      page?.path ?? path,
      state.preference.pages[page?.path ?? path],
    );
  function move(id: string, delta: number) {
    const order = [...pref.order],
      index = order.indexOf(id),
      next = index + delta;
    if (next < 0 || next >= order.length || !page) return;
    [order[index], order[next]] = [order[next], order[index]];
    state.update(page.path, { ...pref, order });
  }
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Personalizar Dashboard">
          <SlidersHorizontal size={16} />
        </Button>
      </SheetTrigger>
      <SheetContent className="overflow-y-auto">
        <SheetTitle>Personalizar Dashboard</SheetTitle>
        <SheetDescription>
          Componentes aprovados. Preferências desta sessão, isoladas por
          usuário, marca e template.
        </SheetDescription>
        {session?.role === "ADMIN" && (
          <Choice
            label="Template"
            value={state.enabled ? "v2" : "v1"}
            options={[
              { value: "v1", label: "Padrão atual · V1" },
              { value: "v2", label: `Gestão ${scope?.operation} · V2` },
            ]}
            onChange={(value) => state.setEnabled(value === "v2")}
          />
        )}
        {session?.role === "ADMIN" && (dataMode === "live" || demoReview) && (
          <Choice
            label="Ambiente de avaliação"
            value={demoReview ? "demo-b2c" : "live-b2b"}
            options={[
              { value: "live-b2b", label: "B2B Live — MX" },
              { value: "demo-b2c", label: "B2C Demo" },
            ]}
            onChange={(value) => {
              if (value === "demo-b2c") {
                reviewB2C();
                router.push("/b2c");
              } else {
                returnToLive();
                router.push("/b2b");
              }
            }}
          />
        )}
        {state.enabled && (
          <>
            <Choice
              label="Página inicial"
              value={
                state.preference.landing ?? `/${scope?.operation.toLowerCase()}`
              }
              options={managerPages
                .filter((p) =>
                  p.path.startsWith(`/${scope?.operation.toLowerCase()}`),
                )
                .map((p) => ({
                  value: p.path,
                  label: `${p.group} · ${p.title}`,
                }))}
              onChange={state.landing}
            />
            {page &&
              pref.order.map((id, index) => (
                <div key={id} className="card glass mt-3">
                  <label className="flex gap-2">
                    <input
                      type="checkbox"
                      checked={!pref.hidden.includes(id)}
                      onChange={(event) =>
                        state.update(page.path, {
                          ...pref,
                          hidden: event.target.checked
                            ? pref.hidden.filter((v) => v !== id)
                            : [...pref.hidden, id],
                        })
                      }
                    />
                    {id === "metrics"
                      ? "Indicadores"
                      : id === "content"
                        ? "Detalhamento"
                        : (WidgetRegistry[id]?.label ?? id)}
                  </label>
                  <div className="flex gap-2 mt-2">
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={index === 0}
                      aria-label={`Subir ${id}`}
                      onClick={() => move(id, -1)}
                    >
                      <ArrowUp size={14} />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={index === pref.order.length - 1}
                      aria-label={`Descer ${id}`}
                      onClick={() => move(id, 1)}
                    >
                      <ArrowDown size={14} />
                    </Button>
                  </div>
                  <Choice
                    label={`Tamanho de ${id}`}
                    value={pref.sizes[id] ?? "full"}
                    options={[
                      { value: "full", label: "Largura completa" },
                      { value: "half", label: "Meia largura" },
                    ]}
                    onChange={(value) =>
                      state.update(page.path, {
                        ...pref,
                        sizes: {
                          ...pref.sizes,
                          [id]: value === "half" ? "half" : "full",
                        },
                      })
                    }
                  />
                </div>
              ))}
            <div className="flex gap-2 mt-4">
              <Button
                variant="outline"
                onClick={() => state.resetPage(page?.path ?? path)}
              >
                Restaurar página
              </Button>
              <Button variant="outline" onClick={state.reset}>
                Restaurar template
              </Button>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
