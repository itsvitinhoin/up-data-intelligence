import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  parseInstallation,
  installationPollingInterval,
  installationPeriodAvailable,
} from "@/services/api/installation";
import { installationKey, readInstallation } from "@/hooks/use-installation";
import { createHttpApi } from "@/services/api/http";
import { handleInstallationBridge } from "@/services/api/installation-bridge.server";
import {
  InstallationStatus,
  InstallationProgressView,
} from "@/components/installation-state";
import { installationFixture } from "./fixtures/installation";
import { defaultFilters } from "@/config/tenants";
import { sessionFor } from "@/services/api";

const scope = {
  tenant_id: "demo-up",
  store_id: "mx-fashion-b2b",
  operation: "B2B" as const,
};
const live = {
  tenant_id: "demo-up",
  store_id: "mx-fashion",
  operation: "B2B" as const,
};
describe("installation contract / UI", () => {
  it.each(["INSTALLING", "PARTIAL", "READY", "BLOCKED"] as const)(
    "renders %s without fabricated percent/ETA",
    (state) => {
      const fixture = installationFixture(state);
      const data = parseInstallation(fixture, "mx-fashion").data;
      const html = renderToStaticMarkup(
        createElement(InstallationStatus, { data, details: true }),
      );
      expect(html).toContain(
        state === "INSTALLING"
          ? "Instalando"
          : state === "PARTIAL"
            ? "Dados parciais"
            : state === "READY"
              ? "Pronto"
              : "Bloqueado",
      );
      expect(html).toContain("300 registros processados");
      expect(html).toContain("Calculando tempo estimado...");
      expect(html).not.toContain("<progress");
    },
  );
  it("handles known denominator and unknown progress separately", () => {
    const progress = {
      kind: "CHUNKS" as const,
      processed: 1,
      total: 2,
      percent: 50,
      eta_seconds: null,
    };
    const fixture = installationFixture();
    fixture.data.progress = progress;
    expect(parseInstallation(fixture).data.progress.percent).toBe(50);
    expect(
      renderToStaticMarkup(
        createElement(InstallationProgressView, { progress }),
      ),
    ).toContain('value="50"');
    progress.percent = 68;
    expect(() => parseInstallation(fixture)).toThrow();
    const unknown = {
      kind: "UNKNOWN" as const,
      processed: null,
      total: null,
      percent: null,
      eta_seconds: null,
    };
    expect(
      renderToStaticMarkup(
        createElement(InstallationProgressView, { progress: unknown }),
      ),
    ).toContain("Calculando progresso...");
  });
  it("rejects percent without denominator, unknown as false, secrets and mismatched stores", () => {
    const fixture = installationFixture();
    fixture.data.progress.percent = 68;
    expect(() => parseInstallation(fixture)).toThrow();
    expect(() =>
      parseInstallation({ ...installationFixture(), secret: "synthetic" }),
    ).toThrow();
    expect(() => parseInstallation(installationFixture(), "another")).toThrow();
    const unknown = installationFixture();
    unknown.data.history_complete = null;
    expect(parseInstallation(unknown).data.history_complete).toBeNull();
    const ready = installationFixture("READY");
    ready.data.history_complete = false;
    expect(() => parseInstallation(ready)).toThrow();
  });
  it.each([
    "backfill",
    "incremental",
    "open_orders",
    "replay",
    "reconcile",
  ] as const)("preserves Orders mode %s", (mode) => {
    const fixture = installationFixture();
    fixture.data.resources.find((r) => r.resource === "orders")!.mode = mode;
    const orders = parseInstallation(fixture).data.resources.find(
      (r) => r.resource === "orders",
    );
    expect(orders?.mode).toBe(mode);
  });
  it("only allows certified exclusive-boundary periods", () => {
    const data = installationFixture().data;
    expect(
      installationPeriodAvailable(data, {
        ...defaultFilters,
        from: "2026-09-01",
        to: "2026-09-27",
      }),
    ).toBe(true);
    expect(
      installationPeriodAvailable(data, {
        ...defaultFilters,
        from: "2026-09-01",
        to: "2026-09-28",
      }),
    ).toBe(false);
    expect(
      installationPeriodAvailable(
        data,
        { ...defaultFilters, from: "2026-09-01", to: "2026-09-27" },
        "performance",
      ),
    ).toBe(false);
    expect(
      installationFixture("INSTALLING", false).data.recommended_preview_window,
    ).toBeNull();
    const outside = installationFixture();
    outside.data.recommended_preview_window!.from = "2026-08-01";
    expect(() => parseInstallation(outside)).toThrow();
  });
  it("polls only installing/partial while consumers are mounted", () => {
    expect(
      installationPollingInterval(installationFixture("INSTALLING").data),
    ).toBe(30000);
    expect(installationPollingInterval(installationFixture().data)).toBe(30000);
    expect(installationPollingInterval(installationFixture("READY").data)).toBe(
      false,
    );
    expect(
      installationPollingInterval(installationFixture("BLOCKED").data),
    ).toBe(false);
    expect(installationPollingInterval()).toBe(false);
  });
  it("keeps cache isolated by principal / tenant / workspace / operation", () => {
    const session = sessionFor("up-admin"),
      key = installationKey(session, scope);
    expect(
      installationKey(session, { ...scope, tenant_id: "another" }),
    ).not.toEqual(key);
    expect(
      installationKey(session, { ...scope, store_id: "another" }),
    ).not.toEqual(key);
    expect(
      installationKey(session, { ...scope, operation: "B2C" }),
    ).not.toEqual(key);
    expect(installationKey({ ...session, id: "another" }, scope)).not.toEqual(
      key,
    );
  });
  it("HTTP client preserves signal/no-store and validates canonical store", async () => {
    const controller = new AbortController();
    const fetcher = vi.fn<typeof fetch>(async () =>
      Response.json(installationFixture()),
    );
    await createHttpApi("http://127.0.0.1:8765", fetcher).installation(live, {
      signal: controller.signal,
    });
    expect(String(fetcher.mock.calls[0]?.[0])).toContain(
      "/v1/stores/mx-fashion/installation",
    );
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      cache: "no-store",
      signal: controller.signal,
    });
    await expect(
      createHttpApi("http://127.0.0.1:8765", fetcher).installation({
        ...live,
        store_id: "other",
      }),
    ).rejects.toThrow();
  });
  it("browser only sends workspace binding and never credentials", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      Response.json(installationFixture()),
    );
    await readInstallation(scope, undefined, fetcher);
    expect(String(fetcher.mock.calls[0]?.[0])).toContain(
      "workspace_operation_id=mx-fashion-b2b",
    );
    expect(String(fetcher.mock.calls[0]?.[0])).not.toContain("store_id=");
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      cache: "no-store",
      credentials: "same-origin",
    });
    await expect(
      readInstallation({ ...scope, operation: "B2C" }, undefined, fetcher),
    ).rejects.toThrow();
  });
  it("only falls back to demo for explicit absent server binding", async () => {
    expect(
      await readInstallation(scope, undefined, async () =>
        Response.json(
          { error: { code: "preview_binding_absent" } },
          { status: 404 },
        ),
      ),
    ).toBeNull();
    await expect(
      readInstallation(scope, undefined, async () =>
        Response.json(
          { error: { code: "store_not_configured" } },
          { status: 404 },
        ),
      ),
    ).rejects.toThrow();
    await expect(
      readInstallation(scope, undefined, async () =>
        Response.json({}, { status: 503 }),
      ),
    ).rejects.toThrow();
  });
  it.each([
    "tenant_id=other&workspace_operation_id=mx-fashion-b2b&operation=B2B",
    "tenant_id=demo-up&workspace_operation_id=mx-fashion-b2c&operation=B2C",
    "tenant_id=demo-up&workspace_operation_id=mx-fashion&operation=B2B",
    "tenant_id=demo-up&workspace_operation_id=mx-fashion-b2b&operation=B2B&store_id=other",
  ])("fails closed for scope/filter %s", async (query) => {
    const read = vi.fn();
    const response = await handleInstallationBridge(
      new Request(`http://127.0.0.1:3100/api/dashboard/installation?${query}`),
      { mode: () => "read-api-preview", readApi: read },
    );
    expect(response.status).toBeGreaterThanOrEqual(400);
    expect(read).not.toHaveBeenCalled();
  });
  it("server resolves canonical store and does not echo failures", async () => {
    const installation = vi.fn<
      ReturnType<typeof createHttpApi>["installation"]
    >(async () => installationFixture());
    const api = { ...createHttpApi("http://127.0.0.1:8765"), installation };
    const request = new Request(
      "http://127.0.0.1:3100/api/dashboard/installation?tenant_id=demo-up&workspace_operation_id=mx-fashion-b2b&operation=B2B",
    );
    const response = await handleInstallationBridge(request, {
      mode: () => "read-api-preview",
      readApi: () => api,
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(installation.mock.calls[0]?.[0]).toEqual(live);
    installation.mockRejectedValueOnce(new Error("synthetic-sensitive"));
    const failed = await handleInstallationBridge(request, {
      mode: () => "read-api-preview",
      readApi: () => api,
    });
    expect(await failed.text()).not.toContain("synthetic-sensitive");
    expect(
      (await handleInstallationBridge(request, { mode: () => "demo" })).status,
    ).toBe(404);
  });
});
