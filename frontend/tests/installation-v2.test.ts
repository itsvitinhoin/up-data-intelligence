import { expect, it } from "vitest";
import {
  parseInstallation,
  installationPollingInterval,
} from "@/services/api/installation";
import { parseOnboarding } from "@/services/api/onboarding";
import { installationV2Fixture } from "./fixtures/installation";
import { onboardingResult } from "./fixtures/onboarding";

it("READY is requested-range completion, not lifetime proof", () => {
  const data = parseInstallation(installationV2Fixture("READY")).data;
  expect(data.history_complete).toBe(false);
  expect(data.progress.percent).toBe(100);
  expect(installationPollingInterval(data)).toBe(false);
});
it("real logical progress, separate counters, null ETA and partial polling", () => {
  const data = parseInstallation(installationV2Fixture()).data;
  expect(data.progress.processed).toBe(18);
  expect(data.progress.total).toBe(61);
  expect(data.progress.percent).toBe((18 / 61) * 100);
  expect(data.records_processed).toBe(344000);
  expect(data.progress.eta_seconds).toBeNull();
  expect(installationPollingInterval(data)).toBe(30000);
});
it("unknown work stops polling and cannot masquerade as READY", () => {
  const state = installationV2Fixture("OUTCOME_UNKNOWN");
  expect(installationPollingInterval(parseInstallation(state).data)).toBe(
    false,
  );
  state.data.overall_state = "READY";
  expect(() => parseInstallation(state)).toThrow();
});
it("rejects unknown fields, wrong store, false 100% and missing publication", () => {
  const value = installationV2Fixture("READY");
  expect(() => parseInstallation(value, "foreign")).toThrow();
  expect(() =>
    parseInstallation({
      ...value,
      data: { ...value.data, execution_name: "not-for-client" },
    }),
  ).toThrow();
  value.data.progress.total = 62;
  expect(() => parseInstallation(value)).toThrow();
  const missing = installationV2Fixture("READY");
  missing.data.available_window = null;
  missing.data.recommended_preview_window = null;
  expect(() => parseInstallation(missing)).toThrow();
});
it("authenticated onboarding readback can carry only validated scoped installation", () => {
  const result = {
    ...onboardingResult(),
    installation: installationV2Fixture(),
  };
  result.installation.data.store_id = "synthetic-brand";
  result.installation.metadata.store_id = "synthetic-brand";
  expect(parseOnboarding(result).installation?.data.progress.kind).toBe(
    "CHUNKS",
  );
  result.installation.metadata.store_id = "foreign";
  expect(() => parseOnboarding(result)).toThrow();
});
