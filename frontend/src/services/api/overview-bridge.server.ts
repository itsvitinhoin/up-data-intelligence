/** Compatibility entry point for the established Overview bridge. */
import { handleReadBridge } from "./read-bridge.server";
import { createServerDashboardReadApi, getDashboardDataMode } from "./server";
export function handleOverviewBridge(
  request: Request,
  dependencies: {
    mode?: typeof getDashboardDataMode;
    readApi?: typeof createServerDashboardReadApi;
  } = {},
) {
  return handleReadBridge(request, "overview", undefined, dependencies);
}
