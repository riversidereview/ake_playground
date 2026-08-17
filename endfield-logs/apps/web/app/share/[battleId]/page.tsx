import { StateBlock } from "../../../components/state-block";
import { fetchApiServer } from "../../../lib/api/server";
import type { ShareSummaryResponse } from "../../../lib/api/types";
import { ShareView } from "./share-view";

type SharePageProps = {
  params: Promise<{ battleId: string }>;
};

export const dynamic = "force-dynamic";

export default async function SharePage({ params }: SharePageProps) {
  const { battleId } = await params;
  try {
    const summary = await fetchApiServer<ShareSummaryResponse>(`/api/battles/${battleId}/share-summary`);
    return <ShareView summary={summary} />;
  } catch (error) {
    return (
      <StateBlock
        title="Share Summary Unavailable"
        description={error instanceof Error ? error.message : "Failed to load battle summary."}
      />
    );
  }
}

export const revalidate = 0;
