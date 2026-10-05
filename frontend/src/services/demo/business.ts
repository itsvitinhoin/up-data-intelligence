import { customerMetrics } from "./customer-metrics";
import { dateRange, DEMO_TODAY, periodDays, inPeriod } from "@/lib/period";
import type {
  Campaign,
  CampaignDetail,
  Customer,
  Geography,
  Influence,
  Metric,
  Order,
  Overview,
  RequestContext,
  Retention,
  TimelineEvent,
} from "@/services/demo/types";
import * as fixtures from "./fixtures";
export function hasDemoData(c: RequestContext) {
  return [
    "mx-fashion-b2b",
    "mx-fashion-b2c",
    "lume-b2b",
    "orla-b2b",
    "orla-b2c",
  ].includes(c.scope.store_id);
}
export function factor(c: RequestContext) {
  return (
    (c.scope.store_id.startsWith("mx-fashion")
      ? 1
      : c.scope.store_id.startsWith("lume")
        ? 0.65
        : 0.42) *
    (c.scope.operation === "B2C" ? 0.4 : 1) *
    (c.filters.channel === "all"
      ? 1
      : c.filters.channel === "meta"
        ? 0.72
        : 0.28) *
    (c.filters.collection === "all"
      ? 1
      : c.filters.collection === "primavera"
        ? 0.62
        : 0.38)
  );
}
export function customersFor(c: RequestContext): Customer[] {
  if (!hasDemoData(c)) return [];
  const prefix = c.scope.store_id.startsWith("mx-fashion")
    ? ""
    : c.scope.store_id.startsWith("lume")
      ? "Lume · "
      : "Orla · ";
  const selectedOrders = ordersFor(c);
  return fixtures.customers
    .filter((customer) =>
      selectedOrders.some((order) => order.customer_id === customer.id),
    )
    .map((r) => ({
      ...r,
      name: prefix + r.name,
      requested: (Number(r.requested) * factor(c)).toFixed(2),
      fulfilled: (Number(r.fulfilled) * factor(c)).toFixed(2),
    }))
    .filter(
      (r) =>
        (!c.filters.search ||
          `${r.name} ${r.city}`
            .toLowerCase()
            .includes(c.filters.search.toLowerCase())) &&
        (!c.filters.state ||
          c.filters.state === "all" ||
          c.filters.state === r.state) &&
        (!c.filters.segment ||
          c.filters.segment === "all" ||
          c.filters.segment === r.segment) &&
        (c.scope.operation === "B2C" ||
          !c.filters.media ||
          c.filters.media === "all" ||
          r.paid === (c.filters.media === "yes")),
    );
}
export function ordersFor(c: RequestContext) {
  if (!hasDemoData(c)) return [];
  return fixtures.orders
    .filter((o) => inPeriod(o.date, c.filters))
    .map((o) => ({
      ...o,
      requested: (Number(o.requested) * factor(c)).toFixed(2),
      fulfilled: (Number(o.fulfilled) * factor(c)).toFixed(2),
    }));
}
export function allOrdersFor(c: RequestContext): Order[] {
  if (!hasDemoData(c)) return [];
  return fixtures.orders.map((o) => ({
    ...o,
    requested: (
      Number(o.requested) *
      factor({
        ...c,
        filters: { ...c.filters, channel: "all", collection: "all" },
      })
    ).toFixed(2),
    fulfilled: (
      Number(o.fulfilled) *
      factor({
        ...c,
        filters: { ...c.filters, channel: "all", collection: "all" },
      })
    ).toFixed(2),
  }));
}
export function total(rows: Order[], key: "requested" | "fulfilled") {
  const cents = rows.reduce((s, o) => s + BigInt(o[key].replace(".", "")), 0n);
  return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}
function campaignOrders(index: number, c: RequestContext) {
  return ordersFor(c)
    .filter((o) => o.paid)
    .filter((order) => {
      const i = fixtures.orders
        .filter((o) => o.paid)
        .findIndex((o) => o.id === order.id);
      return index === 0
        ? i % 2 === 0
        : index === 1
          ? i % 3 !== 0
          : i % 3 === 0;
    });
}
export function campaignsFor(c: RequestContext): Campaign[] {
  if (!hasDemoData(c)) return [];
  return fixtures.campaigns.map((base, i) => {
    const orders = campaignOrders(i, c);
    const requested = total(orders, "requested"),
      fulfilled = total(orders, "fulfilled"),
      spend = (
        (Number(base.spend) *
          factor(c) *
          periodDays(c.filters).filter(
            (day) => day >= "2026-09-01" && day <= "2026-09-30",
          ).length) /
        30
      ).toFixed(2);
    return {
      ...base,
      requested,
      fulfilled,
      spend,
      orders: orders.length,
      customers: new Set(orders.map((o) => o.customer_id)).size,
      newCustomers: null,
      cac: null,
      roasRequested: (Number(requested) / Number(spend)).toFixed(2),
      roasFulfilled: (Number(fulfilled) / Number(spend)).toFixed(2),
    };
  });
}
export function influenceFor(c: RequestContext): Influence {
  const campaigns = campaignsFor(c);
  const unique = new Map<string, Order>();
  campaigns.forEach((_, i) =>
    campaignOrders(i, c).forEach((o) => unique.set(o.id, o)),
  );
  const orders = [...unique.values()];
  const ids = new Set(orders.map((o) => o.customer_id));
  return {
    orders,
    customers: customersFor({
      ...c,
      filters: {
        ...c.filters,
        search: "",
        state: "all",
        segment: "all",
        media: "all",
      },
    }).filter((r) => ids.has(r.id)),
    campaigns,
    requested: total(orders, "requested"),
    fulfilled: total(orders, "fulfilled"),
  };
}
export function campaignFor(
  id: string,
  c: RequestContext,
): CampaignDetail | null {
  const list = campaignsFor(c);
  const i = list.findIndex((r) => r.id === id);
  if (i < 0) return null;
  const orders = campaignOrders(i, c);
  const ids = new Set(orders.map((o) => o.customer_id));
  return {
    campaign: list[i],
    campaigns: [list[i]],
    orders,
    customers: customersFor({
      ...c,
      filters: {
        ...c.filters,
        search: "",
        state: "all",
        segment: "all",
        media: "all",
      },
    })
      .filter((r) => ids.has(r.id))
      .map((r) => ({
        ...r,
        orders: orders.filter((o) => o.customer_id === r.id).length,
        requested: total(
          orders.filter((o) => o.customer_id === r.id),
          "requested",
        ),
        fulfilled: total(
          orders.filter((o) => o.customer_id === r.id),
          "fulfilled",
        ),
      })),
    requested: list[i].requested,
    fulfilled: list[i].fulfilled,
  };
}
export function timelineFor(
  customer: Customer,
  c: RequestContext,
): TimelineEvent[] {
  const base = new Date(customer.firstPurchase + "T12:00:00Z").valueOf();
  const templates = [
    ...fixtures.timeline.slice(0, 4),
    {
      id: "cart",
      type: "cart_created",
      title: "Carrinho criado",
      detail: "Intenção de compra observada",
      evidence: "DIRECT" as const,
    },
    {
      id: "checkout",
      type: "checkout_started",
      title: "Checkout iniciado",
      detail: "Checkout deste cliente",
      evidence: "DIRECT" as const,
    },
    ...fixtures.timeline.slice(4),
  ];
  return templates
    .filter(
      (e) =>
        (customer.paid || e.type !== "paid_touch") &&
        (customer.orders > 1 || e.type !== "repeat_purchase"),
    )
    .map((e, i) => ({
      ...e,
      id: `${c.scope.store_id}:${customer.id}:${e.id}`,
      store_id: c.scope.store_id,
      customer_id: customer.id,
      date: new Date(base + (i - 6) * 3600000).toISOString(),
    }));
}
export function geographyFor(c: RequestContext): Geography[] {
  const customers = customersFor(c),
    orders = ordersFor(c);
  return [...new Set(customers.map((r) => r.state))].map((uf) => {
    const rows = customers.filter((r) => r.state === uf);
    const selected = orders.filter((o) =>
      rows.some((r) => r.id === o.customer_id),
    );
    const requested = Number(total(selected, "requested"));
    return {
      uf,
      approvedWithoutPurchase: null,
      conversionRate: null,
      name: fixtures.geography.find((g) => g.uf === uf)?.name ?? uf,
      requested,
      fulfilled: Number(total(selected, "fulfilled")),
      customers: rows.length,
      orders: selected.length,
      newCustomers: null,
      influencedCustomers: rows.filter((r) => r.paid).length,
      averageTicket: selected.length ? requested / selected.length : null,
      cities: [...new Set(rows.map((r) => r.city))].map((name) => {
        const residents = rows.filter((r) => r.city === name);
        const cityOrders = selected.filter((o) =>
          residents.some((r) => r.id === o.customer_id),
        );
        return {
          name,
          customers: residents.length,
          orders: cityOrders.length,
          requested: Number(total(cityOrders, "requested")),
          fulfilled: Number(total(cityOrders, "fulfilled")),
        };
      }),
    };
  });
}
export function retentionFor(c: RequestContext): Retention[] {
  const customers = customersFor(c);
  const orders = ordersFor(c);
  const purchases = customers.map((customer) =>
    orders
      .filter(
        (o) =>
          o.customer_id === customer.id &&
          [
            "RESERVED",
            "CONFIRMED",
            "PROCESSING",
            "INVOICED",
            "SHIPPED",
          ].includes(o.status),
      )
      .toSorted(
        (a, b) => a.date.localeCompare(b.date) || a.id.localeCompare(b.id),
      ),
  );
  return [1, 2, 3, 4].map((n) => {
    const previous = purchases.filter((p) => p.length >= n).length;
    const gaps = purchases
      .filter((p) => p.length >= n + 1)
      .map(
        (p) =>
          (new Date(p[n].date).valueOf() - new Date(p[n - 1].date).valueOf()) /
          86400000,
      )
      .toSorted((a, b) => a - b);
    const middle = Math.floor(gaps.length / 2);
    return {
      sequence: `Compra ${n} → Compra ${n + 1}${n === 4 ? "+" : ""}`,
      customers: gaps.length,
      mean: gaps.length ? gaps.reduce((s, v) => s + v, 0) / gaps.length : null,
      median: gaps.length
        ? gaps.length % 2
          ? gaps[middle]
          : (gaps[middle - 1] + gaps[middle]) / 2
        : null,
      rate: previous ? Math.round((gaps.length / previous) * 1000) / 10 : 0,
      cohorts: [30, 60, 90, 180, 365].map((day) => ({ day, rate: null })),
    };
  });
}
export function overviewFor(c: RequestContext): Overview {
  const rows = ordersFor(c),
    customers = customersFor(c),
    influence = influenceFor(c);
  const requested = Number(total(rows, "requested")),
    fulfilled = Number(total(rows, "fulfilled"));
  const recurring = customers.filter((r) => r.orders > 1).length;
  const spend = influence.campaigns.reduce((s, p) => s + Number(p.spend), 0);
  const b2b = c.scope.operation === "B2B";
  const metrics: Metric[] = [];
  function m(
    group: Metric["group"],
    label: string,
    value: number | null,
    format: Metric["format"] = "number",
    hint = "Base demonstrativa observada",
  ) {
    metrics.push({
      group,
      label,
      value: value === null ? null : String(value),
      format,
      hint,
    });
  }
  if (b2b) {
    m("Receita", "Faturamento Solicitado", requested, "currency");
    m("Receita", "Faturamento Atendido", fulfilled, "currency");
    m(
      "Receita",
      "Receita Cancelada",
      0,
      "currency",
      "Pedidos CANCELED · nenhum no cenário",
    );
    m("Receita", "Gap Atendimento", requested - fulfilled, "currency");
    m(
      "Receita",
      "Crescimento Receita",
      null,
      "percent",
      "Comparação anterior indisponível",
    );
    m("Pedidos", "Pedidos Solicitados", rows.length);
    m(
      "Pedidos",
      "Pedidos Pagos",
      null,
      "number",
      "Fonte financeira não conectada",
    );
    m("Pedidos", "Pedidos Cancelados", 0);
    m(
      "Pedidos",
      "Ticket Médio Solicitado",
      rows.length ? requested / rows.length : null,
      "currency",
    );
    m(
      "Pedidos",
      "Ticket Médio Atendido",
      rows.length ? fulfilled / rows.length : null,
      "currency",
    );
    m(
      "Pedidos",
      "Peças Solicitadas",
      rows.reduce((s, o) => s + o.requestedQuantity, 0),
    );
    m(
      "Pedidos",
      "Peças Atendidas",
      rows.reduce((s, o) => s + o.fulfilledQuantity, 0),
    );
    m(
      "Pedidos",
      "Peças por Pedido",
      rows.length
        ? rows.reduce((s, o) => s + o.requestedQuantity, 0) / rows.length
        : null,
    );
  } else {
    m("Receita", "Faturamento Captado", requested, "currency");
    m(
      "Receita",
      "Faturamento Aprovado",
      null,
      "currency",
      "Fonte financeira não conectada",
    );
    m(
      "Receita",
      "Receita Cancelada",
      0,
      "currency",
      "Pedidos CANCELED no cenário",
    );
    m(
      "Receita",
      "Receita Aberta",
      null,
      "currency",
      "Não inferir pagamento pelo status comercial",
    );
    m("Pedidos", "Pedidos", rows.length);
    m(
      "Pedidos",
      "Ticket Médio Captado",
      rows.length ? requested / rows.length : null,
      "currency",
    );
    m(
      "Pedidos",
      "Ticket Médio Aprovado",
      null,
      "currency",
      "Fonte financeira não conectada",
    );
  }
  m("Clientes", "Clientes Compradores", customers.length);
  m(
    "Clientes",
    "Clientes Novos",
    null,
    "number",
    "Histórico completo não confirmado",
  );
  m("Clientes", "Clientes Recorrentes", recurring);
  if (b2b)
    m(
      "Clientes",
      "Clientes Reativados",
      null,
      "number",
      "Policy de reativação não definida",
    );
  m(
    "Clientes",
    "% Recompra",
    customers.length ? (recurring / customers.length) * 100 : null,
    "percent",
  );
  if (b2b) {
    m("Mídia", "Clientes influenciados por mídia", influence.customers.length);
    m("Mídia", "Pedidos influenciados por mídia", influence.orders.length);
    m(
      "Mídia",
      "Receita Solicitada Influenciada",
      Number(influence.requested),
      "currency",
      "União de pedidos, sem somar campanhas",
    );
    m(
      "Mídia",
      "Receita Atendida Influenciada",
      Number(influence.fulfilled),
      "currency",
      "União de pedidos, sem somar campanhas",
    );
  }
  m(
    "Mídia",
    b2b ? "ROAS Solicitado" : "ROAS Captado",
    spend ? Number(influence.requested) / spend : null,
    "ratio",
    "Cenário de cobertura sintética; participação, não atribuição",
  );
  m(
    "Mídia",
    b2b ? "ROAS Atendido" : "ROAS Aprovado",
    b2b && spend ? Number(influence.fulfilled) / spend : null,
    "ratio",
    b2b ? "Atendido não significa pago" : "Fonte financeira não conectada",
  );
  if (b2b)
    m(
      "Mídia",
      "CAC Novo Cliente",
      null,
      "currency",
      "Histórico completo não confirmado",
    );
  const select = (label: string, display = label): Metric => ({
    ...metrics.find((item) => item.label === label)!,
    label: display,
  });
  const metric = (
    label: string,
    value: number | null,
    format: Metric["format"],
    hint: string,
  ): Metric => ({
    label,
    value: value === null ? null : String(value),
    format,
    hint,
  });
  const b2bOverview: Overview["b2b"] = b2b
    ? {
        relationship: customerMetrics(
          ordersFor({
            ...c,
            filters: {
              ...c.filters,
              channel: "all",
              media: "all",
              from: "2000-01-01",
              to:
                dateRange(c.filters).to < DEMO_TODAY
                  ? dateRange(c.filters).to
                  : DEMO_TODAY,
            },
          }),
          fixtures.approvals,
          dateRange(c.filters).from,
          dateRange(c.filters).to < DEMO_TODAY
            ? dateRange(c.filters).to
            : DEMO_TODAY,
        ),
        revenue: [
          select("Faturamento Solicitado"),
          select("Faturamento Atendido"),
          metric(
            "% de Atendimento",
            requested ? (fulfilled / requested) * 100 : null,
            "percent",
            "Valor atendido / solicitado · não confirma pagamento",
          ),
          select("Gap Atendimento", "Gap de Atendimento"),
        ],
        orders: [
          select("Pedidos Solicitados"),
          metric(
            "Pedidos Atendidos",
            rows.filter((o) => Number(o.fulfilled) > 0).length,
            "number",
            "Pedidos com valor atendido maior que zero, inclusive parciais",
          ),
          select("Peças por Pedido"),
          select("Ticket Médio Solicitado", "Ticket Médio"),
        ],
        customers: [
          select("Clientes Compradores"),
          {
            ...select("Clientes Novos", "Novos"),
            secondary: {
              label: "Ticket Médio de Aquisição",
              value: null,
              hint: "Primeira compra histórica não confirmada",
            },
          },
          {
            ...select("Clientes Recorrentes", "Recorrentes"),
            secondary: {
              label: "Ticket Médio de Retenção",
              value: null,
              hint: "Aguardando receita e pedidos classificados de recompra",
            },
          },
          {
            ...select("% Recompra", "% de Retenção"),
            hint: "Recorrentes observados / compradores · não é retenção por coorte",
          },
        ],
        media: [
          {
            ...select(
              "Clientes influenciados por mídia",
              "Clientes Atribuídos",
            ),
            hint: "Participação de campanhas na jornada; não atribuição exclusiva",
          },
          {
            ...select("Receita Atendida Influenciada", "Faturamento Atribuído"),
            hint: "Atendido dos pedidos com influência · união sem duplicação",
          },
          metric(
            "Investimento em Mídias",
            spend,
            "currency",
            "Investimento demonstrativo das campanhas",
          ),
          metric(
            "ROI",
            null,
            "percent",
            "Custos e margem não confirmados; ROAS não é ROI",
          ),
        ],
        series: periodDays(c.filters).map((day) => {
          const daily = rows.filter((o) => o.date === day);
          const returningIds = new Set(
            customers
              .filter((customer) => customer.orders > 1)
              .map((customer) => customer.id),
          );
          return {
            date: day.slice(8) + "/" + day.slice(5, 7),
            requested: Number(total(daily, "requested")),
            fulfilled: Number(total(daily, "fulfilled")),
            newCustomers: null,
            recurringCustomers: new Set(
              daily
                .filter((o) => returningIds.has(o.customer_id))
                .map((o) => o.customer_id),
            ).size,
            mediaRevenue: Number(
              total(
                influence.orders.filter((o) => o.date === day),
                "fulfilled",
              ),
            ),
            spend: null,
          };
        }),
        attributedOrders: influence.orders.map((order) => ({
          ...order,
          campaign_names: influence.campaigns
            .filter((_, i) =>
              campaignOrders(i, c).some((o) => o.id === order.id),
            )
            .map((campaign) => campaign.name)
            .join(" · "),
        })),
      }
    : undefined;
  return {
    b2b: b2bOverview,
    metrics,
    goal: { requested, fulfilled },
    series: periodDays(c.filters).map((day) => {
      const orders = rows.filter((o) => o.date === day);
      return {
        date: day.slice(8) + "/" + day.slice(5, 7),
        requested: Number(total(orders, "requested")),
        fulfilled: Number(total(orders, "fulfilled")),
        orders: orders.length,
      };
    }),
    week: ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"].map((day, i) => ({
      day,
      orders: rows.filter(
        (o) => new Date(o.date + "T12:00:00Z").getUTCDay() === i,
      ).length,
    })),
  };
}
