import type { OnboardingResult, OnboardingRequest } from "@/types/onboarding";
export const syntheticCredential = "SYNTHETIC-ONLY-NOT-A-REAL-API-KEY";
export const syntheticOperation = "22222222-2222-4222-8222-222222222222";
export function onboardingResult(): OnboardingResult {
  return {
    operation_id: syntheticOperation,
    store_id: "synthetic-brand",
    brand_id: "brand-synthetic-brand",
    name: "Synthetic Brand",
    tenant_id: "demo-up",
    workspace_operations: [{ id: "synthetic-brand-b2b", operation: "B2B" }],
    status: "INSTALLING",
    current_step: "CONFIGURED",
    error_code: null,
    created_at: "2026-10-02T03:00:00Z",
    updated_at: "2026-10-02T03:00:00Z",
    sources: [{ source: "upzero", state: "PENDING" }],
  };
}
export function onboardingRequest(): OnboardingRequest {
  return {
    tenant_id: "demo-up",
    store: {
      name: "Synthetic Brand",
      slug: "synthetic-brand",
      operation_b2b: true,
      operation_b2c: false,
      timezone: "America/Sao_Paulo",
      currency: "BRL",
      history_from: "2026-01-01",
    },
    sources: {
      upzero: {
        enabled: true,
        credential: syntheticCredential,
        store_identifier: null,
      },
      meta: { enabled: false, account_id: null, api_version: null },
    },
  };
}
