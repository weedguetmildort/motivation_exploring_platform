import { selectedStudy, studyApiPath } from "./studySelection";
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
  study_id?: string;
  study_protocol?: Record<string, unknown>;
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  consent?: boolean;
  consent_given_at?: string;
  consent_text?: string;
  consent_agreed_at?: string;
  consent_declined_at?: string;
  consent_viewed_at?: string;
  consent_abandoned_at?: string;
  last_active_at?: string;
  is_admin: boolean;
  assigned_var?: string | null;

  // Study flow (authoritative). The backend snapshots the participant's whole
  // assigned journey at signup; prefer GET /api/study/next for routing.
  step_order?: string[];
  completed_steps?: string[];
  variant_sequence?: string[];
  study_flow_version?: number;
  demographics_completed?: boolean;
  survey_pre_base_completed?: boolean;
  quiz_base_completed?: boolean;
  survey_post_base_completed?: boolean;
  quiz_variant_completed?: boolean;
  survey_post_variant_completed?: boolean;
  survey_stage?: string;
  followup_study_granted?: boolean;
};

export async function signup(data: SignupPayload) {
  invalidateMeCache();
  const result = await apiFetch<{ user: User }>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({
      first_name: data.firstName,
      last_name: data.lastName,
      email: data.email,
      password: data.password,
      consent: data.consent,
    }),
  });
  invalidateMeCache();
  return result;
}

export async function login(email: string, password: string) {
  invalidateMeCache();
  const result = await apiFetch<{ user: User }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  invalidateMeCache();
  return result;
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
let _meGeneration = 0;
let _meStudy = selectedStudy();

export function invalidateMeCache() {
  _meGeneration += 1;
  _meCache = null;
  _mePending = null;
}

export async function getMe() {
  const study = selectedStudy();
  if (study !== _meStudy) { invalidateMeCache(); _meStudy = study; }
  const now = Date.now();
  if (_meCache && now - _meCache.ts < ME_TTL_MS) {
    return _meCache.value;
  }
  if (_mePending) return _mePending;
  const generation = _meGeneration;
  _mePending = apiFetch<{ user: User }>("/auth/me")
    .then((res) => {
      // A request started before login/logout or a completed study step must
      // not repopulate the cache with the old identity or old progress.
      if (generation === _meGeneration) {
        _meCache = { value: res, ts: Date.now() };
        _mePending = null;
      }
      return res;
    })
    .catch((e) => {
      if (generation === _meGeneration) _mePending = null;
      throw e;
    });
  return _mePending;
}

export async function logout() {
  invalidateMeCache();
  const result = await apiFetch<void>("/auth/logout", { method: "POST" });
  invalidateMeCache();
  return result;
}

export async function recordConsentAgreement(consentText: string) {
  return apiFetch<{ ok: boolean }>("/auth/consent", {
    method: "POST",
    body: JSON.stringify({ consent_text: consentText }),
  });
}

export async function recordConsentDecline(consentText: string) {
  return apiFetch<{ ok: boolean }>("/auth/decline", {
    method: "POST",
    body: JSON.stringify({ consent_text: consentText }),
  });
}

// Funnel telemetry (step 5): the participant reached the consent page.
export async function recordConsentViewed() {
  return apiFetch<{ ok: boolean }>("/auth/consent-viewed", { method: "POST" });
}

// Funnel telemetry (step 6c): the participant is leaving the consent page
// without agreeing/declining. Uses navigator.sendBeacon so the request survives
// the page being torn down (tab close, navigation); the session cookie is sent
// automatically for this same-origin request. Falls back to a keepalive fetch
// where sendBeacon is unavailable. Fire-and-forget — never throws.
export function sendConsentAbandonedBeacon() {
  const url = studyApiPath("/auth/consent-abandoned") as string;
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon(url);
      return;
    }
    fetch(url, { method: "POST", credentials: "include", keepalive: true }).catch(() => {});
  } catch {
    /* on unload there is nothing more we can do */
  }
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
