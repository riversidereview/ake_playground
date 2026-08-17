import { StateBlock } from "../../components/state-block";
import { AdminDashboard } from "../../features/admin/admin-dashboard";
import { fetchApiServer, getCurrentUser } from "../../lib/api/server";
import type { AdminDashboardResponse } from "../../lib/api/types";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const currentUser = await getCurrentUser();

  if (!currentUser) {
    return (
      <StateBlock
        title="需要登录"
        description="后台管理页只对已登录账号开放，请先登录你的站点账号。"
      />
    );
  }

  if (!currentUser.isAdmin) {
    return (
      <StateBlock
        title="没有权限"
        description="当前账号不是管理员，不能查看全站账号和战斗记录后台。"
      />
    );
  }

  try {
    const dashboard = await fetchApiServer<AdminDashboardResponse>("/api/admin/dashboard");
    return <AdminDashboard initialData={dashboard} />;
  } catch (error) {
    return (
      <StateBlock
        title="后台加载失败"
        description={error instanceof Error ? error.message : "暂时无法加载后台数据。"}
      />
    );
  }
}
