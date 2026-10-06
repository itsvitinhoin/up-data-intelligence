import { parseMetadata } from "./http";
import { ApiError } from "./access";
export type CustomerContact = {
  basis: "current_core_profile";
  observed_at: string | null;
  cpf: string | null;
  cnpj: string | null;
  email: string | null;
  phone: string | null;
};
export function parseCustomerContact(value: unknown): CustomerContact {
  const fail = (): never => {
    throw new ApiError(502, "Contato indisponível.");
  };
  if (!value || typeof value !== "object" || Array.isArray(value))
    return fail();
  const row = value as Record<string, unknown>;
  if (
    Object.keys(row).some(
      (key) =>
        !["basis", "observed_at", "cpf", "cnpj", "email", "phone"].includes(
          key,
        ),
    ) ||
    row.basis !== "current_core_profile"
  )
    return fail();
  for (const field of ["cpf", "cnpj", "email", "phone", "observed_at"])
    if (
      row[field] !== null &&
      (typeof row[field] !== "string" || (row[field] as string).length > 320)
    )
      return fail();
  if (
    row.observed_at !== null &&
    !Number.isFinite(Date.parse(String(row.observed_at)))
  )
    return fail();
  return row as CustomerContact;
}

export function decodeContactEnvelope(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new ApiError(502, "Contato indisponível.");
  const row = value as Record<string, unknown>;
  if (Object.keys(row).some((key) => !["data", "metadata"].includes(key)))
    throw new ApiError(502, "Contato indisponível.");
  return {
    data: parseCustomerContact(row.data),
    metadata: parseMetadata(row.metadata),
  };
}
