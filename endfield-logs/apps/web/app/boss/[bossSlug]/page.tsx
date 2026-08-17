import { StateBlock } from "../../../components/state-block";
import { fetchApiServer } from "../../../lib/api/server";
import type { BossRankingResponse } from "../../../lib/api/types";
import { BossRankingView } from "./boss-ranking-view";

type BossPageProps = {
  params: Promise<{ bossSlug: string }>;
  searchParams: Promise<{ metric?: "dps" | "rdps" }>;
};

export const dynamic = "force-dynamic";

export default async function BossRankingPage({ params, searchParams }: BossPageProps) {
  const { bossSlug } = await params;
  const resolvedSearchParams = await searchParams;
  const metric = resolvedSearchParams.metric === "rdps" ? "rdps" : "dps";

  try {
    const [ranking, hotBosses] = await Promise.all([
      fetchApiServer<BossRankingResponse>(`/api/bosses/${bossSlug}/rankings?metric=${metric}`),
      fetchApiServer<
        {
          bossSlug: string;
          bossName: string;
          dungeonName: string;
        }[]
      >("/api/home/hot-bosses"),
    ]);

    return <BossRankingView hotBosses={hotBosses} metric={metric} ranking={ranking} />;
  } catch (error) {
    return (
      <StateBlock
        title="Leaderboard Unavailable"
        description={error instanceof Error ? error.message : "Failed to load leaderboard data."}
      />
    );
  }
}

export const revalidate = 0;
