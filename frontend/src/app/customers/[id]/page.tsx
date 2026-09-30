import { Application } from "@/features/application";
import { CustomerDetailPage } from "@/features/customer-pages";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Application>
      <CustomerDetailPage id={id} />
    </Application>
  );
}
