import BossCharacterStatisticsPage from "../boss/[bossSlug]/statistics/page";

import type { BossCharacterStatisticsResponse } from "../../lib/api/types";

type StatisticsSearchParams = Promise<{
  metric?: BossCharacterStatisticsResponse["metric"];
  range?: BossCharacterStatisticsResponse["range"];
  potential?: BossCharacterStatisticsResponse["potential"];
}>;

export const dynamic = "force-dynamic";

export default async function CharacterStatisticsOverviewPage({
  searchParams,
}: {
  searchParams: StatisticsSearchParams;
}) {
  return BossCharacterStatisticsPage({
    params: Promise.resolve({ bossSlug: "__all__" }),
    searchParams,
  });
}

export const revalidate = 0;
