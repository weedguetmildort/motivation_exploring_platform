// frontend/lib/auth.ts

import { apiFetch } from "./fetcher";

type SignupPayload = {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  consent: boolean;
};

export type User = {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  consent?: boolean;
  consent_given_at?: string;
  consent_text?: string;
  consent_agreed_at?: string;
  is_admin: boolean;
  assigned_var?: string | null;
  demographics_completed?: boolean;
  survey_pre_base_completed?: boolean;
  quiz_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  quiz_variant_completed?: boolean;
  survey_post_variant_completed?: boolean;
  survey_stage?: string;
};

export async function signup(data: SignupPayload) {
  return apiFetch<{ user: User }>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({
      first_name: data.firstName,
      last_name: data.lastName,
      email: data.email,
      password: data.password,
      consent: data.consent,
    }),
  });
}

export async function login(email: string, password: string) {
  invalidateMeCache();
  return apiFetch<{ user: User }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// ---------------------------------------------------------------------------
// getMe() deduplication + short-lived cache
// - In-flight dedup: two calls fired at the same time (React StrictMode double
//   mount) share one network request instead of making two.
// - TTL cache: page navigations within 30 s skip the network entirely.
// - Invalidated by logout() and login() so stale data never lingers.
// ---------------------------------------------------------------------------
const ME_TTL_MS = 30_000;

let _meCache: { value: { user: User }; ts: number } | null = null;
let _mePending: Promise<{ user: User }> | null = null;

export function invalidateMeCache() {
  _meCache = null;
  _mePending = null;
}

export async function getMe() {
  const now = Date.now();
  if (_meCache && now - _meCache.ts < ME_TTL_MS) {
    return _meCache.value;
  }
  if (_mePending) return _mePending;
  _mePending = apiFetch<{ user: User }>("/auth/me")
    .then((res) => {
      _meCache = { value: res, ts: Date.now() };
      _mePending = null;
      return res;
    })
    .catch((e) => {
      _mePending = null;
      throw e;
    });
  return _mePending;
}

export async function logout() {
  invalidateMeCache();
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export async function recordConsentAgreement(consentText: string) {
  return apiFetch<{ ok: boolean }>("/auth/consent", {
    method: "POST",
    body: JSON.stringify({ consent_text: consentText }),
  });
}

export async function changePassword(currentPassword: string, newPassword: string) {
  return apiFetch<{ ok: boolean }>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}