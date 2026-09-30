import { demoApi } from "@/services/demo/adapter";
/** Explicit demo composition root. Replace only after response mapping/auth contracts are approved. */
export const api = demoApi;

// Composition root for the separate UP administration and demo identity boundaries.
export {
  adminApi,
  authorizedTenants,
  demoUsers,
  sessionFor,
} from "@/services/demo/admin";
