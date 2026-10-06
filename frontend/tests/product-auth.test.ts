import { metadata as contactMetadata } from "./fixtures/restoration";
import { describe, it, expect, vi, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import {
  assertCsrf,
  authMutation,
  liveRead,
  liveOnboarding,
  sessionResponse,
  csrfResponse,
  type PrivateCaller,
} from "@/services/auth/bff.server";
import { catalogView, parseCatalog } from "@/services/auth/catalog";
import { getDashboardDataMode } from "@/services/api/server";
import { readOverview } from "@/hooks/use-overview-data";
const token = "a".repeat(64);
const catalog = {
  data: {
    role: "CLIENT_USER",
    tenants: ["tenant-a"],
    workspaces: [
      {
        tenant_id: "tenant-a",
        brand_id: "brand-a",
        workspace_operation_id: "workspace-a",
        operation: "B2B",
      },
    ],
  },
};
const scope =
  "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B";
function request(
  path: string,
  method = "GET",
  body?: unknown,
  extra: Record<string, string> = {},
) {
  return new Request("https://web.example.test" + path, {
    method,
    headers: {
      cookie: `__Host-up_session=verified-session; __Host-up_csrf=${token}`,
      origin: "https://web.example.test",
      "sec-fetch-site": "same-origin",
      "x-up-csrf": token,
      "content-type": "application/json",
      ...extra,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
afterEach(() => vi.unstubAllEnvs());
describe("authenticated product BFF", () => {
  it("enables live independently of preview and production loopback guards", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DASHBOARD_DATA_MODE", "live");
    expect(getDashboardDataMode()).toBe("live");
  });
  it("uses catalog grants only and contains no technical store/email", () => {
    const c = parseCatalog(catalog);
    expect(catalogView(c).session.role).toBe("VIEWER");
    expect(JSON.stringify(c)).not.toContain("store_id");
    expect(() =>
      parseCatalog({
        ...catalog,
        data: {
          ...catalog.data,
          workspaces: [...catalog.data.workspaces, ...catalog.data.workspaces],
        },
      }),
    ).toThrow();
    expect(() =>
      parseCatalog({
        ...catalog,
        data: {
          ...catalog.data,
          workspaces: [{ ...catalog.data.workspaces[0], tenant_id: "other" }],
        },
      }),
    ).toThrow();
  });
  it("requires exact origin, same site and double submit", () => {
    expect(() =>
      assertCsrf(request("/api/auth/session", "POST")),
    ).not.toThrow();
    const invalidHeaders: Record<string, string>[] = [
      { origin: "https://evil.example" },
      { "sec-fetch-site": "cross-site" },
      { "x-up-csrf": "b".repeat(64) },
      { cookie: "__Host-up_session=verified-session" },
    ];
    for (const header of invalidHeaders)
      expect(() =>
        assertCsrf(request("/api/auth/session", "POST", {}, header)),
      ).toThrow();
    expect(() =>
      assertCsrf(
        new Request("http://web.example.test/api/auth/session", {
          method: "POST",
        }),
      ),
    ).toThrow();
  });
  it("issues secure host-only CSRF without making real session JS-readable", async () => {
    const r = csrfResponse(request("/api/auth/csrf"));
    expect(r.headers.get("set-cookie")).toContain("__Host-up_csrf=");
    expect(r.headers.get("set-cookie")).toContain(
      "Secure; SameSite=Strict; Path=/",
    );
    expect(r.headers.get("set-cookie")).not.toContain("__Host-up_session");
  });
  it("checks the public HTTPS authority behind Cloud Run TLS termination", () => {
    vi.stubEnv("K_SERVICE", "up-web");
    const headers = new Headers(request("/api/auth/session", "POST").headers);
    headers.set("host", "up-web-123456.southamerica-east1.run.app");
    headers.set("origin", "https://up-web-123456.southamerica-east1.run.app");
    headers.set("x-forwarded-proto", "https");
    const proxied = () =>
      new Request("https://0.0.0.0:8080/api/auth/session", {
        method: "POST",
        headers,
      });
    expect(() => assertCsrf(proxied())).not.toThrow();
    expect(csrfResponse(proxied()).status).toBe(200);
    headers.set("origin", "https://different.run.app");
    expect(() => assertCsrf(proxied())).toThrow();
    headers.set("origin", "https://up-web-123456.southamerica-east1.run.app");
    headers.set("x-forwarded-host", "attacker.example");
    expect(() => assertCsrf(proxied())).not.toThrow();
    headers.set("host", "attacker.example");
    expect(() => assertCsrf(proxied())).toThrow();
    headers.set("host", "up-web-123456.southamerica-east1.run.app");
    headers.set("x-forwarded-proto", "http");
    expect(() => assertCsrf(proxied())).toThrow();
  });
  it("sets a twelve-hour HttpOnly server session, never JSON", async () => {
    const call: PrivateCaller = vi.fn().mockResolvedValue(
      new Response("{}", {
        headers: {
          "set-cookie":
            "__Host-up_session=server-cookie; Secure; HttpOnly; Path=/",
        },
      }),
    );
    const r = await authMutation(
      request("/api/auth/session", "POST", { id_token: "temporary-id-token" }),
      "session",
      call,
    );
    expect(r.status).toBe(200);
    expect(r.headers.get("set-cookie")).toContain(
      "Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200",
    );
    expect(await r.text()).not.toContain("server-cookie");
    expect(call).toHaveBeenCalledTimes(1);
  });
  it("POST logout clears cookie only after private revocation succeeds", async () => {
    const call: PrivateCaller = vi.fn().mockResolvedValue(
      new Response("{}", {
        headers: {
          "set-cookie": "__Host-up_session=; Secure; HttpOnly; Path=/",
        },
      }),
    );
    const r = await authMutation(
      request("/api/auth/logout", "POST", {}),
      "logout",
      call,
    );
    expect(r.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(
      (await authMutation(request("/api/auth/logout"), "logout", call)).status,
    ).toBe(405);
    expect(call).toHaveBeenCalledTimes(1);
  });
  it("rejects missing CSRF before any auth/admin upstream call", async () => {
    const call = vi.fn();
    const r = request(
      "/api/auth/session",
      "POST",
      { id_token: "temporary" },
      { "x-up-csrf": "" },
    );
    expect((await authMutation(r, "session", call)).status).toBe(403);
    expect(
      (
        await liveOnboarding(
          request("/api/admin/onboarding", "POST", {}, { "x-up-csrf": "" }),
          undefined,
          call,
        )
      ).status,
    ).toBe(403);
    expect(call).not.toHaveBeenCalled();
  });
  it.each([401, 403])(
    "preserves denied authorization %s without demo fallback",
    async (status) => {
      const call = vi.fn().mockResolvedValue(new Response("{}", { status }));
      expect(
        (await sessionResponse(request("/api/session"), call)).status,
      ).toBe(status);
    },
  );
  it("private API denial survives scope tampering without a redundant catalog request", async () => {
    const call = vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code: "workspace_forbidden" } },
          { status: 403 },
        ),
      );
    expect(
      (
        await liveRead(
          request(
            "/api/dashboard/overview?" + scope.replace("workspace-a", "other"),
          ),
          "overview",
          undefined,
          call,
        )
      ).status,
    ).toBe(403);
    expect(call).toHaveBeenCalledTimes(1);
    expect(
      (
        await liveRead(
          request(
            "/api/dashboard/overview?" + scope + "&store_id=technical-other",
          ),
          "overview",
          undefined,
          call,
        )
      ).status,
    ).toBe(400);
    expect(call).toHaveBeenCalledTimes(1);
  });
  it("client admin POST is denied before durable mutation", async () => {
    const call = vi.fn().mockResolvedValue(Response.json(catalog));
    expect(
      (
        await liveOnboarding(
          request("/api/admin/onboarding", "POST", { tenant_id: "tenant-a" }),
          undefined,
          call,
        )
      ).status,
    ).toBe(403);
    expect(call).toHaveBeenCalledTimes(1);
  });
  it("validates real metadata and preserves decimal money and lifetime NULLs", async () => {
    const envelope = {
      data: {
        requested_revenue: "123456789012345.12",
        fulfilled_revenue: "98765.43",
        fulfillment_rate: null,
        fulfillment_gap: null,
        cancelled_requested_revenue: "0.00",
        orders_requested: 2,
        orders_cancelled: 0,
        buyers_observed: 2,
        recurring_buyers_observed: 0,
        purchase_frequency_observed: "1",
        new_customers_confirmed: null,
        ltv_complete: null,
        cac: null,
        revenue_paid: null,
        series: [],
      },
      pagination: null,
      metadata: {
        contract_version: "1.0.0",
        store_id: "synthetic-technical-store",
        generation: 17,
        policy_hash: "a".repeat(64),
        currency: "BRL",
        reporting_timezone: "America/Sao_Paulo",
        as_of: "2026-10-03T03:00:00Z",
        report_from: "2026-09-01",
        report_to: "2026-10-03",
        history_complete: false,
        facts_complete: true,
        limitations: ["history_incomplete"],
      },
    };
    const call = vi.fn().mockResolvedValueOnce(Response.json(envelope));
    const result = await liveRead(
      request("/api/dashboard/overview?" + scope + "&to=2026-10-02"),
      "overview",
      undefined,
      call,
    );
    expect(result.status).toBe(200);
    expect(await result.json()).toEqual(envelope);
    expect(call.mock.calls[0][1]).toContain("to=2026-10-03");
    expect(call.mock.calls[0][1]).not.toContain("store_id=");
    expect(result.headers.get("cache-control")).toBe("private, no-store");
    expect(call).toHaveBeenCalledTimes(1);
    expect(call.mock.calls[0][1]).not.toBe("/v1/session");
    expect(result.headers.get("server-timing")).toMatch(/^bff;dur=\d+/);
  });
  it("B2C has no silent demo", async () => {
    const c = {
      data: {
        ...catalog.data,
        workspaces: [{ ...catalog.data.workspaces[0], operation: "B2C" }],
      },
    };
    const call = vi.fn().mockResolvedValue(Response.json(c));
    expect(
      (
        await liveRead(
          request("/api/dashboard/overview?" + scope.replace("B2B", "B2C")),
          "overview",
          undefined,
          call,
        )
      ).status,
    ).toBe(424);
    expect(call).not.toHaveBeenCalled();
  });
  it("source architecture uses memory persistence and clears SDK, never token React state or browser storage", () => {
    const s = readFileSync("src/services/auth/client.ts", "utf8");
    expect(s).toContain("inMemoryPersistence");
    expect(s).toContain("initializeAuth");
    expect(s).not.toMatch(
      /getAuth|browserLocalPersistence|indexedDBLocalPersistence/,
    );
    expect(s).toContain("await signOut(auth)");
    expect(s).not.toMatch(/localStorage|sessionStorage|useState/);
    expect(s).toContain("sendEmailVerification");
    expect(s).toContain("sendPasswordResetEmail");
  });
  it("live Overview 404 never becomes demo", async () => {
    const c = {
      scope: {
        tenant_id: "tenant-a",
        store_id: "workspace-a",
        workspace_operation_id: "workspace-a",
        operation: "B2B" as const,
      },
      session: {
        id: "authenticated-session",
        name: "UP",
        role: "ADMIN" as const,
        tenant_ids: ["tenant-a"],
        store_ids: ["workspace-a"],
      },
      filters: { days: 30, channel: "all", collection: "all" },
    };
    await expect(
      readOverview(
        "live",
        c,
        vi
          .fn()
          .mockResolvedValue(
            Response.json(
              { error: { code: "preview_binding_absent" } },
              { status: 404 },
            ),
          ),
      ),
    ).rejects.toThrow();
  });
  it("bounds streamed bodies and rejects malformed JSON before exchange", async () => {
    const call = vi.fn();
    for (const [body, status] of [
      ["{bad-json", 400],
      ["x".repeat(16385), 413],
    ] as const) {
      const source = request("/api/auth/session", "POST", {});
      const malformed = new Request(source.url, {
        method: "POST",
        headers: source.headers,
        body,
      });
      expect((await authMutation(malformed, "session", call)).status).toBe(
        status,
      );
    }
    expect(call).not.toHaveBeenCalled();
  });
  it("rejects unexpected catalog metadata instead of exposing it", () => {
    expect(() => parseCatalog({ ...catalog, secret: "forbidden" })).toThrow();
    expect(() =>
      parseCatalog({ data: { ...catalog.data, technical_store: "forbidden" } }),
    ).toThrow();
  });
  it("rejects every demo hook entry point in live even if accidentally invoked", async () => {
    const { requireDemoResource } = await import("@/hooks/use-resource");
    expect(() => requireDemoResource("live")).toThrow(
      "Cobertura ainda não certificada",
    );
    expect(() => requireDemoResource("demo")).not.toThrow();
    expect(() => requireDemoResource("read-api-preview")).not.toThrow();
  });
  it("clears an expired cookie but never hides an unknown revocation", async () => {
    const expired = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 401 }));
    const r = await authMutation(
      request("/api/auth/logout", "POST"),
      "logout",
      expired,
    );
    expect(r.headers.get("set-cookie")).toContain("Max-Age=0");
    const unknown = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 503 }));
    const failed = await authMutation(
      request("/api/auth/logout", "POST"),
      "logout",
      unknown,
    );
    expect(failed.status).toBe(503);
    expect(failed.headers.has("set-cookie")).toBe(false);
    expect(unknown).toHaveBeenCalledTimes(1);
  });
});
describe("detail-only contact and safe diagnostics", () => {
  it("does not call upstream without a session and never accepts browser technical store", async () => {
    const call = vi.fn();
    expect(
      (
        await liveRead(
          new Request(
            "https://web.example.test/api/dashboard/customers/x/contact?" +
              scope,
          ),
          "customerContact",
          "x",
          call,
        )
      ).status,
    ).toBe(401);
    expect(
      (
        await liveRead(
          request(
            "/api/dashboard/customers/x/contact?" + scope + "&store_id=other",
          ),
          "customerContact",
          "x",
          call,
        )
      ).status,
    ).toBe(400);
    expect(call).not.toHaveBeenCalled();
  });
  it("validates the strict contact DTO and returns no-store numeric timings only", async () => {
    const contact = {
      basis: "current_core_profile",
      observed_at: null,
      cpf: null,
      cnpj: null,
      email: "synthetic@example.invalid",
      phone: null,
    };
    const call: PrivateCaller = async () =>
      Response.json(
        { data: contact, pagination: null, metadata: contactMetadata },
        {
          headers: {
            "Server-Timing":
              "auth;dur=2, bq;dur=3, serialization;dur=1, api_total;dur=6, secret;desc=forbidden, scope;dur=1",
          },
        },
      );
    const res = await liveRead(
      request("/api/dashboard/customers/x/contact?" + scope),
      "customerContact",
      "x",
      call,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Cache-Control")).toBe("private, no-store");
    const timing = res.headers.get("Server-Timing")!;
    expect(timing).toContain("serialization;dur=1");
    expect(timing).toContain("bff_serialization;dur=");
    expect(timing).not.toMatch(/forbidden|scope|synthetic/);
    expect((await res.json()).data).toEqual(contact);
    const paginatedContact: PrivateCaller = async () =>
      Response.json({
        data: contact,
        pagination: { next_cursor: "not-a-contact-list" },
        metadata: contactMetadata,
      });
    expect(
      (
        await liveRead(
          request("/api/dashboard/customers/x/contact?" + scope),
          "customerContact",
          "x",
          paginatedContact,
        )
      ).status,
    ).toBe(503);
    const outerLeak: PrivateCaller = async () =>
      Response.json({
        data: contact,
        metadata: contactMetadata,
        credential: "forbidden",
      });
    expect(
      (
        await liveRead(
          request("/api/dashboard/customers/x/contact?" + scope),
          "customerContact",
          "x",
          outerLeak,
        )
      ).status,
    ).toBe(503);
    const invalid: PrivateCaller = async () =>
      Response.json({
        data: { ...contact, access_token: "forbidden" },
        metadata: contactMetadata,
      });
    expect(
      (
        await liveRead(
          request("/api/dashboard/customers/x/contact?" + scope),
          "customerContact",
          "x",
          invalid,
        )
      ).status,
    ).toBe(503);
  });
});
