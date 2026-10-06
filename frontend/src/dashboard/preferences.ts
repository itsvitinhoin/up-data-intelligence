import {
  managerPage,
  pageWidgetIds,
  type TemplateId,
  type WidgetSize,
} from "./registry";
export type PagePreference = {
  order: string[];
  hidden: string[];
  sizes: Record<string, WidgetSize>;
};
export type Preference = {
  landing?: string;
  pages: Record<string, PagePreference>;
};
export function preferenceKey(
  user: string,
  tenant: string,
  workspace: string,
  template: TemplateId,
) {
  return JSON.stringify([user, tenant, workspace, template]);
}
export function validatedPagePreference(
  path: string,
  candidate?: PagePreference,
): PagePreference {
  const page = managerPage(path),
    allowed = page ? pageWidgetIds(page) : [];
  const order = [
    ...new Set([
      ...(candidate?.order ?? []).filter((id) => allowed.includes(id)),
      ...allowed,
    ]),
  ];
  return {
    order,
    hidden: [
      ...new Set(
        (candidate?.hidden ?? []).filter((id) => allowed.includes(id)),
      ),
    ],
    sizes: Object.fromEntries(
      Object.entries(candidate?.sizes ?? {}).filter(
        ([id, size]) => allowed.includes(id) && ["full", "half"].includes(size),
      ),
    ),
  };
}
