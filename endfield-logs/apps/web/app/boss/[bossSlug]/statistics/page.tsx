import { StateBlock } from "../../../../components/state-block";
import { fetchApiServer } from "../../../../lib/api/server";
import type { BossCharacterStatisticsResponse } from "../../../../lib/api/types";
import { StatisticsView } from "./statistics-view";

type StatisticsRange = BossCharacterStatisticsResponse["range"];
type StatisticsMetric = BossCharacterStatisticsResponse["metric"];
type StatisticsPotential = BossCharacterStatisticsResponse["potential"];

type BossStatisticsPageProps = {
  params: Promise<{ bossSlug: string }>;
  searchParams: Promise<{ metric?: StatisticsMetric; range?: StatisticsRange; potential?: StatisticsPotential }>;
};

function parseRange(value: string | undefined): StatisticsRange {
  return value === "7d" || value === "14d" || value === "30d" ? value : "all";
}

function parsePotential(value: string | undefined): StatisticsPotential {
  return value === "0" || value === "1-5" ? value : "all";
}

export const dynamic = "force-dynamic";

export default async function BossCharacterStatisticsPage({ params, searchParams }: BossStatisticsPageProps) {
  const { bossSlug } = await params;
  const resolvedSearchParams = await searchParams;
  const metric: StatisticsMetric = resolvedSearchParams.metric === "rdps" ? "rdps" : "dps";
  const timeRange = parseRange(resolvedSearchParams.range);
  const potentialRange = parsePotential(resolvedSearchParams.potential);
  const isAllScope = bossSlug === "__all__";

  try {
    const statistics = await fetchApiServer<BossCharacterStatisticsResponse>(
      isAllScope
        ? `/api/bosses/character-statistics?metric=${metric}&range=${timeRange}&potential=${potentialRange}`
        : `/api/bosses/${bossSlug}/character-statistics?metric=${metric}&range=${timeRange}&potential=${potentialRange}`,
    );

    return (
      <StatisticsView
        bossSlug={bossSlug}
        metric={metric}
        potentialRange={potentialRange}
        statistics={statistics}
        timeRange={timeRange}
      />
    );
  } catch (error) {
    return (
      <StateBlock
        title="Statistics Unavailable"
        description={error instanceof Error ? error.message : "Failed to load character statistics."}
      />
    );
  }
}

export const revalidate = 0;
