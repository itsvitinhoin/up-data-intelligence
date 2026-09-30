import { Application } from "@/features/application";
import { ErpPage } from "@/features/erp";
export default function Page() {
  return (
    <Application>
      <ErpPage view="overview" />
    </Application>
  );
}
