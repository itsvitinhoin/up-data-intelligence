import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { getDashboardDataMode } from "@/services/api/server";
import {
  federationConfig,
  serviceAuthorization,
} from "@/services/auth/service-identity.server";
import {
  catalogCompanies,
  catalogView,
  parseCatalog,
} from "@/services/auth/catalog";

const env: NodeJS.ProcessEnv = {
  NODE_ENV: "test",
  VERCEL: "1",
  VERCEL_ENV: "production",
  GCP_PROJECT_ID: "synthetic-project",
  GCP_PROJECT_NUMBER: "123456789012",
  GCP_WORKLOAD_IDENTITY_POOL_ID: "synthetic-pool",
  GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID: "synthetic-production",
  GCP_SERVICE_ACCOUNT_EMAIL:
    "up-product-vercel-dev@synthetic-project.iam.gserviceaccount.com",
  UP_READ_SERVICE_URL: "https://synthetic-read.run.app",
  UP_ADMIN_SERVICE_URL: "https://synthetic-admin.run.app",
};
afterEach(() => vi.unstubAllEnvs());
describe("Vercel private service identity", () => {
  it("forces live mode and security headers on Vercel even when configuration is missing", () => {
    vi.stubEnv("VERCEL", "1");
    vi.stubEnv("DASHBOARD_DATA_MODE", "demo");
    expect(getDashboardDataMode()).toBe("live");
    const response = proxy(new NextRequest("https://synthetic.vercel.app"));
    expect(response.headers.get("Content-Security-Policy")).toContain(
      "frame-ancestors 'none'",
    );
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
  });
  it("uses federation only for the approved audience and never invokes ADC on Vercel", async () => {
    const federated = vi.fn(async () => "synthetic-ephemeral-identity"),
      cloudRun = vi.fn();
    expect(
      await serviceAuthorization(env.UP_READ_SERVICE_URL!, {
        env,
        federated,
        cloudRun,
      }),
    ).toBe("Bearer synthetic-ephemeral-identity");
    expect(federated).toHaveBeenCalledWith(env.UP_READ_SERVICE_URL);
    expect(cloudRun).not.toHaveBeenCalled();
  });
  it("cannot fall back to ADC after a federation failure", async () => {
    const cloudRun = vi.fn();
    await expect(
      serviceAuthorization(env.UP_READ_SERVICE_URL!, {
        env,
        federated: async () => {
          throw new Error("synthetic_sts_denied");
        },
        cloudRun,
      }),
    ).rejects.toThrow("synthetic_sts_denied");
    expect(cloudRun).not.toHaveBeenCalled();
  });
  it("rejects foreign targets before token acquisition", async () => {
    const federated = vi.fn();
    await expect(
      serviceAuthorization("https://foreign.run.app", { env, federated }),
    ).rejects.toThrow("private_service_audience_forbidden");
    expect(federated).not.toHaveBeenCalled();
  });
  it.each([
    { VERCEL_ENV: "development" },
    { GCP_PROJECT_NUMBER: "123/x" },
    { GCP_WORKLOAD_IDENTITY_POOL_ID: "../../foreign" },
    {
      GCP_SERVICE_ACCOUNT_EMAIL:
        "foreign@synthetic-project.iam.gserviceaccount.com",
    },
  ])("fails closed on invalid server federation configuration %j", (change) => {
    expect(() => federationConfig({ ...env, ...change })).toThrow(
      "vercel_federation_configuration_required",
    );
  });
  it("retains ADC only for the temporary approved Cloud Run web runtime", async () => {
    const cloudRun = vi.fn(async () => "synthetic-cloud-run-identity"),
      federated = vi.fn();
    expect(
      await serviceAuthorization(env.UP_READ_SERVICE_URL!, {
        env: { ...env, VERCEL: undefined, K_SERVICE: "up-web" },
        cloudRun,
        federated,
      }),
    ).toBe("Bearer synthetic-cloud-run-identity");
    expect(federated).not.toHaveBeenCalled();
    await expect(
      serviceAuthorization(env.UP_READ_SERVICE_URL!, {
        env: { ...env, VERCEL: undefined },
        cloudRun,
      }),
    ).rejects.toThrow("serving_identity_required");
  });
  it("does not accept empty service identity", async () => {
    await expect(
      serviceAuthorization(env.UP_READ_SERVICE_URL!, {
        env,
        federated: async () => "",
      }),
    ).rejects.toThrow("private_service_identity_unavailable");
  });
});
describe("canonical admin projection", () => {
  it("keeps tenant identity and unavailable brand fields without demo enrichment", () => {
    const catalog = parseCatalog({
      data: {
        role: "ADMIN_UP",
        tenants: ["one", "two"],
        workspaces: [
          {
            tenant_id: "one",
            brand_id: "brand-same",
            workspace_operation_id: "workspace-one",
            operation: "B2B",
          },
          {
            tenant_id: "two",
            brand_id: "brand-same",
            workspace_operation_id: "workspace-two",
            operation: "B2B",
          },
        ],
      },
    });
    const brands = catalogCompanies(catalogView(catalog).tenants);
    expect(brands.map((b) => b.tenant_id)).toEqual(["one", "two"]);
    for (const b of brands)
      expect(b).toMatchObject({
        platform: null,
        erp: null,
        createdAt: null,
        cnpj: "",
        logo: "",
      });
    expect(brands).toHaveLength(2);
  });
  it("keeps the existing AdminShell instead of the rejected replacement", () => {
    const shell = readFileSync("src/components/shell.tsx", "utf8");
    expect(shell).toContain("<AdminShell>");
    expect(shell).not.toContain("LiveBrands");
    const admin = readFileSync("src/features/brand-integrations.tsx", "utf8");
    expect(admin).toContain("workspace-grid brand-integrations");
    expect(admin).toContain("catalogCompanies(tenants)");
    expect(admin).toContain("requireDemoResource(dataMode)");
  });
});
