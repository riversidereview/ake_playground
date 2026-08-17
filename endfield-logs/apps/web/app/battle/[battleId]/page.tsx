import { BattleDetailView } from "../../../features/battle-detail/battle-detail-view";
import { StateBlock } from "../../../components/state-block";
import { fetchApiServer } from "../../../lib/api/server";
import type { BattleDetailResponse } from "../../../lib/api/types";

type BattlePageProps = {
  params: Promise<{ battleId: string }>;
  searchParams: Promise<{ metric?: "dps" | "rdps" }>;
};

export const dynamic = "force-dynamic";

export default async function BattleDetailPage({ params, searchParams }: BattlePageProps) {
  const { battleId } = await params;
  const resolvedSearchParams = await searchParams;
  const metric = resolvedSearchParams.metric === "rdps" ? "rdps" : "dps";
  try {
    const detail = await fetchApiServer<BattleDetailResponse>(`/api/battles/${battleId}`);
    return <BattleDetailView detail={detail} metric={metric} />;
  } catch (error) {
    return (
      <StateBlock
        title="战斗详情暂时不可用"
        description={error instanceof Error ? error.message : "战斗详情加载失败。"}
      />
    );
  }
}

export const revalidate = 0;
