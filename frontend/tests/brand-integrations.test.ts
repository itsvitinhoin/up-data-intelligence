import { describe, expect, it, vi } from "vitest";
import {
  parseBrandSummaries,
  parseIntegrationHealth,
  readIntegrationHealth,
} from "@/services/api/brand-integrations";
import {
  liveBrandSummaries,
  liveIntegrationHealth,
} from "@/services/auth/bff.server";
import {
  brandSummariesFixture,
  integrationHealthFixture,
} from "./fixtures/brand-integrations";
const req = (path: string) =>
  new Request(`https://web.example.test${path}`, {
    headers: { cookie: "__Host-up_session=verified-session" },
  });
const scope =
  "tenant_id=synthetic-tenant&workspace_operation_id=synthetic-workspace&operation=B2B";
describe("authenticated brand operational metadata", () => {
  it("validates envelope and preserves unknown creation date", () => {
    const result = parseBrandSummaries(brandSummariesFixture());
    expect(result.data[0].created_at).toBeNull();
    expect(result.data[0].active_connections).toBe(2);
  });
  it("rejects duplicate identities, secrets and inconsistent counts", () => {
    const v = brandSummariesFixture();
    expect(() =>
      parseBrandSummaries({ ...v, data: [...v.data, ...v.data] }),
    ).toThrow();
    expect(() =>
      parseBrandSummaries({
        ...v,
        data: [{ ...v.data[0], secret_resource_name: "not-permitted" }],
      }),
    ).toThrow();
    expect(() =>
      parseBrandSummaries({
        ...v,
        data: [{ ...v.data[0], active_connections: 7 }],
      }),
    ).toThrow();
  });
  it("requests one private metadata resource with no catalog N+1", async () => {
    const call = vi.fn(async () => Response.json(brandSummariesFixture()));
    const response = await liveBrandSummaries(req("/api/admin/brands"), call);
    expect(response.status).toBe(200);
    expect(call).toHaveBeenCalledTimes(1);
    expect(call.mock.calls[0]).toEqual([
      "read",
      "/v1/admin/brands",
      expect.any(Request),
    ]);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
  it("propagates private authorization denial and rejects technical scope before IO", async () => {
    const call = vi.fn(async () =>
      Response.json({ error: { code: "admin_up_required" } }, { status: 403 }),
    );
    expect(
      (await liveBrandSummaries(req("/api/admin/brands"), call)).status,
    ).toBe(403);
    call.mockClear();
    expect(
      (
        await liveIntegrationHealth(
          req(`/api/admin/integrations/health?${scope}&store_id=other`),
          call,
        )
      ).status,
    ).toBe(400);
    expect(call).not.toHaveBeenCalled();
  });
  it("validates health and never turns unknown next sync or counters into zero", () => {
    const value = integrationHealthFixture();
    const result = parseIntegrationHealth({
      ...value,
      data: { ...value.data, blocking_findings: null },
    });
    expect(result.data.next_sync_at).toBeNull();
    expect(result.data.blocking_findings).toBeNull();
  });
  it("rejects mismatched health scope at BFF and presenter", async () => {
    const value = integrationHealthFixture();
    value.data.workspace_operation_id = "another-workspace";
    const call = vi.fn(async () => Response.json(value));
    expect(
      (
        await liveIntegrationHealth(
          req(`/api/admin/integrations/health?${scope}`),
          call,
        )
      ).status,
    ).toBe(503);
    const summary = parseBrandSummaries(brandSummariesFixture()).data[0];
    await expect(
      readIntegrationHealth(
        summary,
        undefined,
        vi.fn(async () => Response.json(value)),
      ),
    ).rejects.toThrow();
  });
});
