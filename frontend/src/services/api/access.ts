import type { RequestContext } from "@/types/domain";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function assertAccess(
  { scope, session }: RequestContext,
  admin = false,
) {
  if (!session?.id) throw new ApiError(401, "Entre novamente para continuar.");
  if (
    !session.tenant_ids.includes(scope.tenant_id) ||
    !session.store_ids.includes(scope.store_id)
  )
    throw new ApiError(
      403,
      "Esta operação não está disponível para seu perfil.",
    );
  if (admin && session.role !== "ADMIN")
    throw new ApiError(
      403,
      "Apenas administradores podem alterar esta configuração.",
    );
}
