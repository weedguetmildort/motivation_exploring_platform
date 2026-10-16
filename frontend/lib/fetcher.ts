import { studyApiPath } from "./studySelection";
// Tiny fetch wrapper that always sends/receives JSON and includes cookies
// Make sure the backend sets an HTTP-only session in dev cookie on login/signup

export class ApiError extends Error {
  constructor(message: string, public status: number, public url: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T = any>(
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<T> {
  const scopedInput = studyApiPath(input);
  const res = await fetch(scopedInput, {
    ...init,
    credentials: "include", // send cookies
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });

  // Try to parse JSON even on non-2xx for better error messages
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* ignore parse error; keep raw text */
  }

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      `${res.status} ${res.statusText}`;
    const url = typeof scopedInput === "string" ? scopedInput : scopedInput instanceof URL ? scopedInput.href : scopedInput.url;
    throw new ApiError(message, res.status, url);
  }

  return data as T;
}
