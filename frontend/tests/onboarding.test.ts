import { afterEach, describe, expect, it, vi } from "vitest";
import { parseOnboarding, submitOnboarding } from "@/services/api/onboarding";
import {
  handleOnboardingBridge,
  onboardingDevEnabled,
} from "@/services/api/onboarding-bridge.server";
import {
  onboardingRequest,
  onboardingResult,
  syntheticCredential,
  syntheticOperation,
} from "./fixtures/onboarding";
const config = () => ({
  base: "http://127.0.0.1:8766",
  token: "SYNTHETIC-ADMIN-TOKEN-NOT-REAL-32-BYTES",
});
function request(extra: RequestInit = {}) {
  return new Request("http://127.0.0.1:3115/api/admin/onboarding", {
    method: "POST",
    headers: {
      Origin: "http://127.0.0.1:3115",
      "Content-Type": "application/json",
      "Idempotency-Key": syntheticOperation,
    },
    body: JSON.stringify(onboardingRequest()),
    ...extra,
  });
}
afterEach(() => vi.unstubAllEnvs());
describe("secure onboarding contract", () => {
  it("validates safe response; refuses credential/reference echo and bad workspace binding", () => {
    expect(parseOnboarding(onboardingResult()).status).toBe("INSTALLING");
    expect(() =>
      parseOnboarding({
        ...onboardingResult(),
        credential: syntheticCredential,
      }),
    ).toThrow();
    expect(() =>
      parseOnboarding({
        ...onboardingResult(),
        secret_resource_name: "synthetic",
      }),
    ).toThrow();
    const bad = onboardingResult();
    bad.workspace_operations[0]!.id = bad.store_id;
    expect(() => parseOnboarding(bad)).toThrow();
  });
  it.each([true, false])(
    "POST uses body only and clears secret after settle (ok=%s)",
    async (ok) => {
      const payload = onboardingRequest();
      const calls: [string, RequestInit | undefined][] = [];
      const fetcher: typeof fetch = async (input, init) => {
        calls.push([String(input), init]);
        return Response.json(
          ok ? onboardingResult() : { error: { code: syntheticCredential } },
          { status: ok ? 201 : 503 },
        );
      };
      if (ok)
        await submitOnboarding(payload, syntheticOperation, undefined, fetcher);
      else
        await expect(
          submitOnboarding(payload, syntheticOperation, undefined, fetcher),
        ).rejects.toThrow(/Cadastro não concluído/);
      expect(payload.sources.upzero.credential).toBeNull();
      expect(calls[0]![0]).not.toContain(syntheticCredential);
      expect(calls[0]![1]).toMatchObject({
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
      });
      expect(calls[0]![1]!.body).toContain(syntheticCredential);
    },
  );
  it("feature defaults closed and cannot enable production", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("UP_ADMIN_ONBOARDING_DEV", "");
    expect(onboardingDevEnabled()).toBe(false);
    vi.stubEnv("UP_ADMIN_ONBOARDING_DEV", "1");
    expect(onboardingDevEnabled()).toBe(true);
    vi.stubEnv("NODE_ENV", "production");
    expect(onboardingDevEnabled()).toBe(false);
  });
  it("bridge forwards only server token and idempotency, never browser auth", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      Response.json(onboardingResult()),
    );
    const req = request();
    req.headers.set("Authorization", "synthetic-browser-auth");
    const response = await handleOnboardingBridge(req, undefined, {
      config,
      fetcher,
    });
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual(onboardingResult());
    expect(fetcher.mock.calls[0]![1]!.headers).toEqual({
      "Content-Type": "application/json",
      "X-UP-Admin-Preview-Token": config().token,
      "Idempotency-Key": syntheticOperation,
    });
    expect(response.headers.get("cache-control")).toContain("no-store");
  });
  it.each(["disabled", "origin", "cross-site", "type", "oversized", "method"])(
    "rejects %s before upstream I/O",
    async (kind) => {
      const req = request();
      const fetcher = vi.fn<typeof fetch>();
      if (kind === "origin")
        req.headers.set("Origin", "https://foreign.invalid");
      if (kind === "cross-site")
        req.headers.set("sec-fetch-site", "cross-site");
      if (kind === "type") req.headers.set("content-type", "text/plain");
      if (kind === "oversized") req.headers.set("content-length", "32769");
      const actual =
        kind === "method"
          ? new Request(req.url, { method: "GET", headers: req.headers })
          : req;
      const response = await handleOnboardingBridge(actual, undefined, {
        config: kind === "disabled" ? () => null : config,
        fetcher,
      });
      expect(response.status).toBeGreaterThanOrEqual(400);
      expect(fetcher).not.toHaveBeenCalled();
    },
  );
  it("sanitizes upstream exception/response with synthetic secret", async () => {
    const response = await handleOnboardingBridge(request(), undefined, {
      config,
      fetcher: async () => {
        throw new Error(syntheticCredential);
      },
    });
    expect(await response.text()).not.toContain(syntheticCredential);
  });
  it("supports safe operation readback with explicit same-origin evidence", async () => {
    const fetcher = vi.fn<typeof fetch>(async () =>
      Response.json(onboardingResult()),
    );
    const req = new Request(
      `http://127.0.0.1:3115/api/admin/onboarding/${syntheticOperation}`,
      { headers: { "sec-fetch-site": "same-origin" } },
    );
    expect(
      (
        await handleOnboardingBridge(req, syntheticOperation, {
          config,
          fetcher,
        })
      ).status,
    ).toBe(200);
    expect(String(fetcher.mock.calls[0]![0])).toContain(
      `/v1/admin/onboarding/${syntheticOperation}`,
    );
  });
});
