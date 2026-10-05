import { describe, it, expect, vi } from "vitest";
import {
  parseConnections,
  parseConnectionResult,
} from "../src/services/api/connections";
import { parseHistory } from "../src/services/api/history";
import {
  liveHistory,
  liveConnectionConfiguration,
} from "../src/services/auth/bff.server";
const scope =
  "tenant_id=tenant-a&workspace_operation_id=workspace-a&operation=B2B";
const connections = {
  data: {
    tenant_id: "tenant-a",
    workspace_operation_id: "workspace-a",
    providers: [
      {
        provider: "upzero",
        status: "active",
        credential_configured: true,
        connection_id: "connection-a",
        store_identifier: null,
        account_id: null,
        api_version: null,
      },
      {
        provider: "meta",
        status: "active",
        credential_configured: true,
        connection_id: "connection-b",
        store_identifier: null,
        account_id: "act_synthetic",
        api_version: "v23.0",
      },
    ],
  },
};
const historyPlan = {
  plan_id: "a".repeat(64),
  purpose: "HISTORY_EXTENSION",
  provider: "upzero",
  status: "RUNNING",
  requested_from: "2026-08-01T03:00:00Z",
  target_as_of: "2026-09-01T03:00:00Z",
  requested_at: "2026-10-05T12:00:00Z",
  error_code: null,
  progress: {
    kind: "CHUNKS",
    processed: 0,
    total: 63,
    percent: 0,
    eta_seconds: null,
  },
  work: { pending: 63, running: 0, complete: 0, blocked: 0, ambiguous: 0 },
  resources: [
    { resource: "orders", total: 31, complete: 0 },
    { resource: "analytics_facts", total: 31, complete: 0 },
    { resource: "publication", total: 1, complete: 0 },
  ],
};
function request(path: string, body?: object, csrf = true) {
  return new Request("https://preview.invalid" + path + "?" + scope, {
    method: body ? "POST" : "GET",
    headers: {
      cookie: `__Host-up_session=synthetic; __Host-up_csrf=${"a".repeat(64)}`,
      origin: "https://preview.invalid",
      "sec-fetch-site": "same-origin",
      "Content-Type": "application/json",
      ...(csrf ? { "X-UP-CSRF": "a".repeat(64) } : {}),
      "Idempotency-Key": "00000000-0000-4000-8000-000000000001",
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}
describe("connection contract and history", () => {
  it("exposes configured state without any secret/reference field", () => {
    expect(
      parseConnections(connections).data.providers[0].credential_configured,
    ).toBe(true);
    const unsafe = structuredClone(connections);
    Object.assign(unsafe.data.providers[0], {
      secret_resource_name: "forbidden",
    });
    expect(() => parseConnections(unsafe)).toThrow();
    expect(() =>
      parseConnectionResult({
        data: {
          operation_id: "a".repeat(64),
          provider: "upzero",
          action: "rotate",
          status: "COMPLETE",
          error_code: null,
          updated_at: "2026-10-05T12:00Z",
          credential: "forbidden",
        },
      }),
    ).toThrow();
  });
  it("validates history chunks/null ETA without manufacturing current coverage", () => {
    expect(
      parseHistory({ data: [historyPlan] }).data[0].progress.eta_seconds,
    ).toBeNull();
    const bad = structuredClone(historyPlan);
    bad.progress.percent = 20;
    expect(() => parseHistory({ data: [bad] })).toThrow();
    expect(() => parseHistory({ data: [historyPlan, historyPlan] })).toThrow();
    expect(() =>
      parseHistory({ data: [{ ...historyPlan, store_id: "foreign" }] }),
    ).toThrow();
  });
  it.each([liveHistory, liveConnectionConfiguration])(
    "rejects missing CSRF before private IO",
    async (handler) => {
      const call = vi.fn();
      const res = await handler(
        request(
          "/api/admin/integrations/configuration",
          { provider: "upzero", action: "disable", credential: null },
          false,
        ),
        call,
      );
      expect(res.status).toBe(403);
      expect(call).not.toHaveBeenCalled();
    },
  );
  it.each([liveHistory, liveConnectionConfiguration])(
    "cannot forward browser technical store scope",
    async (handler) => {
      const call = vi.fn();
      const res = await handler(
        new Request(
          "https://preview.invalid/api/admin/integrations/history?" +
            scope +
            "&store_id=foreign",
          { headers: { cookie: "__Host-up_session=synthetic" } },
        ),
        call,
      );
      expect(res.status).toBe(400);
      expect(call).not.toHaveBeenCalled();
    },
  );
  it("sends bounded dates to private admin and validates persisted receipt", async () => {
    const call = vi
      .fn()
      .mockResolvedValue(Response.json({ data: historyPlan }, { status: 202 }));
    const res = await liveHistory(
      request("/api/admin/integrations/history", {
        provider: "upzero",
        from: "2026-08-01",
        to: "2026-08-31",
      }),
      call,
    );
    expect(res.status).toBe(202);
    expect(call).toHaveBeenCalledTimes(1);
    expect(call.mock.calls[0][0]).toBe("admin");
  });
  it("never retries an ambiguous credential write or returns a credential", async () => {
    const call = vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code: "secret_write_outcome_unknown" } },
          { status: 503 },
        ),
      );
    const res = await liveConnectionConfiguration(
      request("/api/admin/integrations/configuration", {
        provider: "upzero",
        action: "rotate",
        credential: "synthetic-not-real",
      }),
      call,
    );
    expect(res.status).toBe(503);
    expect(call).toHaveBeenCalledTimes(1);
    expect(await res.text()).not.toContain("synthetic-not-real");
  });
});

it("accepts source-specific Meta addition with no per-brand credential", async () => {
  const result = {
    data: {
      operation_id: "b".repeat(64),
      provider: "meta",
      action: "add",
      status: "COMPLETE",
      error_code: null,
      updated_at: "2026-10-05T12:00:00Z",
    },
  };
  const call = vi.fn().mockResolvedValue(Response.json(result));
  const res = await liveConnectionConfiguration(
    request("/api/admin/integrations/configuration", {
      provider: "meta",
      action: "add",
      account_id: "1234567",
      api_version: "v23.0",
    }),
    call,
  );
  expect(res.status).toBe(200);
  expect(call).toHaveBeenCalledTimes(1);
  expect(parseConnectionResult(await res.json()).data.action).toBe("add");
  expect(
    parseHistory({
      data: [
        { ...historyPlan, provider: "meta", purpose: "META_SOURCE_ADDITION" },
      ],
    }).data[0].purpose,
  ).toBe("META_SOURCE_ADDITION");
});
it.each([
  {
    provider: "meta",
    action: "add",
    account_id: "1234567",
    api_version: "v23.0",
    credential: "forbidden",
  },
  {
    provider: "google",
    action: "add",
    account_id: "1234567",
    api_version: "v23.0",
  },
  {
    provider: "meta",
    action: "add",
    account_id: "act_1234567",
    api_version: "latest",
  },
])(
  "rejects unsupported source addition before private IO %j",
  async (value) => {
    const call = vi.fn();
    const res = await liveConnectionConfiguration(
      request("/api/admin/integrations/configuration", value),
      call,
    );
    expect(res.status).toBe(400);
    expect(call).not.toHaveBeenCalled();
  },
);
