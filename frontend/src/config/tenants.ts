import type { Tenant } from "@/types/domain";
export const tenants: Tenant[] = [
  {
    id: "demo-up",
    name: "Grupo UP · Demo",
    brands: [
      {
        id: "demo-mx",
        name: "MX Fashion",
        operations: [
          { id: "mx-fashion-b2b", type: "B2B" },
          { id: "mx-fashion-b2c", type: "B2C" },
        ],
      },
      {
        id: "demo-lume",
        name: "Lume Studio",
        operations: [{ id: "lume-b2b", type: "B2B" }],
      },
    ],
  },
  {
    id: "demo-horizonte",
    name: "Horizonte · Demo",
    brands: [
      {
        id: "demo-orla",
        name: "Orla",
        operations: [
          { id: "orla-b2b", type: "B2B" },
          { id: "orla-b2c", type: "B2C" },
        ],
      },
    ],
  },
];
export const defaultFilters = {
  days: 30 as const,
  channel: "all",
  collection: "all",
  search: "",
  state: "all",
  segment: "all",
  media: "all",
};
