import { Application } from "@/features/application";
import { CampaignDetailPage } from "@/features/influence";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <Application>
      <CampaignDetailPage id={id} />
    </Application>
  );
}
