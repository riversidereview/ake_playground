import { StateBlock } from "../../../components/state-block";
import { fetchApiServer } from "../../../lib/api/server";
import type { PublicUserRankingsResponse } from "../../../lib/api/types";
import { AccountRecordsView } from "./account-records-view";

type AccountRecordsPageProps = {
  params: Promise<{ accountId: string }>;
};

export const dynamic = "force-dynamic";

export default async function AccountRecordsPage({ params }: AccountRecordsPageProps) {
  const { accountId } = await params;

  try {
    const response = await fetchApiServer<PublicUserRankingsResponse>(
      `/api/battles/users/${encodeURIComponent(accountId)}/rankings`,
    );

    return <AccountRecordsView response={response} />;
  } catch (error) {
    return (
      <StateBlock
        title="Account Rankings Unavailable"
        description={error instanceof Error ? error.message : "Failed to load account rankings."}
      />
    );
  }
}
