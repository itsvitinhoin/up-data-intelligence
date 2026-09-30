import { describe, expect, it } from "vitest";
import { verifiedConnectionCount } from "@/lib/brand-connection";
import { adminApi, sessionFor } from "@/services/demo/admin";
import type { Company } from "@/types/domain";

const brand = (id: string): Company => ({
  id,
  name: "Marca sintética",
  cnpj: "DEMO",
  logo: "",
  segment: "Moda",
  operation: "B2C",
  status: "ACTIVE",
  meta_account_id: null,
});

describe("brand cards", () => {
  it("never treats a prepared integration as a verified live connection", () => {
    const prepared: Company = {
      ...brand("prepared"),
      integrations: [
        { provider: "Meta Ads", enabled: true, accountId: "demo" },
      ],
      activeConnections: 0,
    };
    expect(verifiedConnectionCount(prepared)).toBe(0);
    expect(verifiedConnectionCount({ ...prepared, activeConnections: 2 })).toBe(
      2,
    );
    expect(
      verifiedConnectionCount({ ...prepared, activeConnections: -1 }),
    ).toBe(0);
  });

  it("records the creation date once and keeps connection status server-owned", async () => {
    const session = sessionFor("up-admin");
    const id = `synthetic-${crypto.randomUUID()}`;
    await adminApi.saveBrand(
      {
        ...brand(id),
        createdAt: "2000-01-01T00:00:00Z",
        activeConnections: 9,
      },
      session,
    );
    const created = (await adminApi.brands(session)).find(
      (item) => item.id === id,
    )!;
    expect(created.createdAt).not.toBe("2000-01-01T00:00:00Z");
    expect(Number.isNaN(Date.parse(created.createdAt!))).toBe(false);
    expect(created.activeConnections).toBe(0);
    await adminApi.saveBrand(
      {
        ...created,
        name: "Marca sintética editada",
        createdAt: null,
        activeConnections: 5,
      },
      session,
    );
    const updated = (await adminApi.brands(session)).find(
      (item) => item.id === id,
    )!;
    expect(updated.createdAt).toBe(created.createdAt);
    expect(updated.activeConnections).toBe(0);
  });
});
