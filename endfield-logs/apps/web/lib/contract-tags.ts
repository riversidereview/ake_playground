import type { ContractTag } from "./api/types";

export function hasContractTagData(score?: number | null, tags?: ContractTag[] | null) {
  return (tags?.length ?? 0) > 0 || (score ?? 0) > 0;
}
