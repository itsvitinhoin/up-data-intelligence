import { Application } from "@/features/application";
import { ProductsPage } from "@/features/commerce";
export default function Page() {
  return (
    <Application>
      <ProductsPage inventory />
    </Application>
  );
}
