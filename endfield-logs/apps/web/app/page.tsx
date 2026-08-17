import { StateBlock } from "../components/state-block";
import { fetchPublicApiServer } from "../lib/api/public-server";
import type { HotBossCard } from "../lib/api/types";
import { HomeView } from "./home-view";

export const revalidate = 30;

export default async function HomePage() {
  try {
    const hotBosses = await fetchPublicApiServer<HotBossCard[]>("/api/home/hot-bosses", {
      next: { revalidate },
    });
    return <HomeView hotBosses={hotBosses} />;
  } catch (error) {
    return (
      <StateBlock
        title="Failed to Load Home Data"
        description={error instanceof Error ? error.message : "Temporarily unable to load homepage records."}
      />
    );
  }
}
