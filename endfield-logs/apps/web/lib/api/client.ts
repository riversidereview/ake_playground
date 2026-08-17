const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ?? "";

export const API_BASE_URL = configuredApiBaseUrl.replace(/\/+$/, "");

export function buildApiUrl(path: string): string {
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

export async function fetchApi<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildApiUrl(path), {
    cache: "no-store",
    ...init,
  });
  if (!response.ok) {
    let message = `接口请求失败：${response.status}`;
    try {
      const data = (await response.json()) as { error?: { message?: string } };
      message = data.error?.message ?? message;
    } catch {
      // Ignore JSON parse errors and keep the generic message.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}
