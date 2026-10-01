/** Temporary DEV binding. Workspace IDs never become canonical data store IDs. */
import type { LiveScope } from "./http";

export type WorkspaceOperationScope = {
  tenant_id: string;
  workspace_operation_id: string;
  operation: "B2B" | "B2C";
};
export type DashboardStoreBinding = WorkspaceOperationScope & {
  data_store_id: string;
};

const devBindings: readonly DashboardStoreBinding[] = [
  {
    tenant_id: "demo-up",
    workspace_operation_id: "mx-fashion-b2b",
    operation: "B2B",
    data_store_id: "mx-fashion",
  },
];

export function resolveDevOverviewBinding(
  scope: WorkspaceOperationScope,
): DashboardStoreBinding | null {
  if (typeof window !== "undefined")
    throw new Error("Store binding is server-only");
  return (
    devBindings.find(
      (binding) =>
        binding.tenant_id === scope.tenant_id &&
        binding.workspace_operation_id === scope.workspace_operation_id &&
        binding.operation === scope.operation,
    ) ?? null
  );
}

export function toReadScope(binding: DashboardStoreBinding): LiveScope {
  return {
    tenant_id: binding.tenant_id,
    store_id: binding.data_store_id,
    operation: "B2B",
  };
}
