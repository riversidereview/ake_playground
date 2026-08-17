import { StateBlock } from "../../components/state-block";
import { UserBattlesDashboard } from "../../features/records/user-battles-dashboard";
import { fetchApiServer, getCurrentUser } from "../../lib/api/server";
import type { UserBattlesResponse } from "../../lib/api/types";

export const dynamic = "force-dynamic";

export default async function RecordsPage() {
  const currentUser = await getCurrentUser();

  if (!currentUser) {
    return (
      <StateBlock
        title="需要登录"
        description="我的记录页只对已登录账号开放，请先登录你的站点账号。"
      />
    );
  }

  try {
    const response = await fetchApiServer<UserBattlesResponse>("/api/battles/mine");
    return (
      <UserBattlesDashboard
        battles={response.battles}
        currentUser={currentUser}
        rankings={response.rankings}
      />
    );
  } catch (error) {
    return (
      <StateBlock
        title="记录加载失败"
        description={error instanceof Error ? error.message : "暂时无法加载你的战斗记录。"}
      />
    );
  }
}
