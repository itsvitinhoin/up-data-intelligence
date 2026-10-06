"use client";
import { createContext, useContext, useState, type ReactNode } from "react";
import { useWorkspace } from "@/features/providers";
import { managerPages, templateFor, type TemplateId } from "./registry";
import {
  preferenceKey,
  validatedPagePreference,
  type Preference,
  type PagePreference,
} from "./preferences";
const Context = createContext<ReturnType<typeof useTemplateState> | null>(null);
function useTemplateState(initial: boolean) {
  const { session, scope } = useWorkspace();
  const [versions, setVersions] = useState<Record<string, boolean>>({});
  const [preferences, setPreferences] = useState<Record<string, Preference>>(
    {},
  );
  const identity = JSON.stringify([
    session?.id,
    scope?.tenant_id,
    scope?.workspace_operation_id ?? scope?.store_id,
    scope?.operation,
  ]);
  const enabled = versions[identity] ?? initial;
  const template: TemplateId =
    enabled && scope ? templateFor(scope.operation) : "current-standard.v1";
  const key = preferenceKey(
    session?.id ?? "",
    scope?.tenant_id ?? "",
    scope?.workspace_operation_id ?? scope?.store_id ?? "",
    template,
  );
  const preference = preferences[key] ?? { pages: {} };
  return {
    enabled,
    template,
    preference,
    setEnabled: (value: boolean) =>
      setVersions((previous) => ({ ...previous, [identity]: value })),
    update: (path: string, page: PagePreference) =>
      setPreferences((previous) => ({
        ...previous,
        [key]: {
          ...(previous[key] ?? { pages: {} }),
          pages: {
            ...(previous[key]?.pages ?? {}),
            [path]: validatedPagePreference(path, page),
          },
        },
      })),
    landing: (path: string) => {
      if (
        !managerPages.some(
          (p) =>
            p.path === path &&
            path.startsWith(`/${scope?.operation.toLowerCase()}`),
        )
      )
        return;
      setPreferences((previous) => ({
        ...previous,
        [key]: { ...(previous[key] ?? { pages: {} }), landing: path },
      }));
    },
    resetPage: (path: string) =>
      setPreferences((previous) => ({
        ...previous,
        [key]: {
          ...(previous[key] ?? { pages: {} }),
          pages: Object.fromEntries(
            Object.entries(previous[key]?.pages ?? {}).filter(
              ([id]) => id !== path,
            ),
          ),
        },
      })),
    reset: () =>
      setPreferences((previous) => ({ ...previous, [key]: { pages: {} } })),
  };
}
export function TemplateProvider({
  children,
  initial,
}: {
  children: ReactNode;
  initial: boolean;
}) {
  const value = useTemplateState(initial);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useTemplate() {
  const value = useContext(Context);
  if (!value) throw new Error("Template provider required");
  return value;
}
