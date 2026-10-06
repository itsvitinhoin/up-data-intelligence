import { Application } from "@/features/application";
import { Empty } from "@/components/ui-kit";
export default function Page() {
  return (
    <Application>
      <Empty
        title="Template de gestão"
        description="Selecione o template V2 em Personalizar Dashboard para acessar esta visualização."
      />
    </Application>
  );
}
