import type { Company } from "@/types/domain";

/** Only the verified count supplied by the service can mark a brand connected. */
export function verifiedConnectionCount(brand: Company): number {
  const count = brand.activeConnections;
  return typeof count === "number" && Number.isSafeInteger(count) && count > 0
    ? count
    : 0;
}
