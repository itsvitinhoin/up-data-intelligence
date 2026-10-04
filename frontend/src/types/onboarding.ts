import type { InstallationEnvelope } from "./installation";
export type OnboardingRequest = {
  tenant_id: string;
  store: {
    name: string;
    slug: string;
    operation_b2b: boolean;
    operation_b2c: boolean;
    timezone: string;
    currency: string;
    history_from: string;
    qualifying_order_statuses: string[];
  };
  sources: {
    upzero: {
      enabled: boolean;
      credential: string | null;
      store_identifier: string | null;
    };
    meta: {
      enabled: boolean;
      account_id: string | null;
      api_version: string | null;
    };
  };
};
export type OnboardingResult = {
  installation?: InstallationEnvelope;
  operation_id: string;
  store_id: string;
  brand_id: string;
  name: string;
  tenant_id: string;
  workspace_operations: { id: string; operation: "B2B" | "B2C" }[];
  status:
    | "RESERVED"
    | "SECRET_PENDING"
    | "SECRET_READY"
    | "FINALIZING"
    | "INSTALLING"
    | "READY"
    | "BLOCKED";
  current_step: string;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  sources: { source: "upzero" | "meta"; state: "PENDING" | "ACTIVE" }[];
};
