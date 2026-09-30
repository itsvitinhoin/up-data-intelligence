import { describe, expect, it } from "vitest";
import { recordColumns } from "@/lib/list-export";
import { csvContent } from "@/lib/erp-export";
import { platforms, erps } from "@/types/domain";
describe("shared export contracts", () => {
  it("keeps unknowns blank and never exports credentials, logos or arbitrary payloads", () => {
    const rows = [
      {
        name: "=1+1",
        value: null,
        count: 0,
        active: false,
        logo: "binary",
        access_token: "private",
        password: "private",
        payload: { secret: "private" },
      },
    ];
    const columns = recordColumns(rows);
    expect(columns.map((c) => c.header)).toEqual([
      "name",
      "value",
      "count",
      "active",
    ]);
    const csv = csvContent(rows, columns);
    expect(csv).toContain("'=1+1");
    expect(csv).toContain('"0";"false"');
    expect(csv).not.toContain("private");
  });
  it("uses the exact requested platform and ERP choices", () => {
    expect(platforms).toEqual([
      "UP Zero",
      "Vesti",
      "Nuvemshop",
      "Shopify",
      "Outros",
    ]);
    expect(erps).toEqual(["Miré", "Mansé", "Bling", "Shop9", "Outros"]);
  });
});
