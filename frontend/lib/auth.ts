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
  is_admin: boolean;
  assigned_var?: string | null;
  demographics_completed?: boolean;

  // Study flow (authoritative). Prefer /api/study/next over reading these
  // directly — the backend owns the "where next" decision.
  step_order?: string[];
  completed_steps?: string[];
  variant_sequence?: string[];
  study_flow_version?: number;

  // Derived legacy mirrors. Kept for display/analytics; not used for routing.
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
  return apiFetch<{ user: User }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe() {
  return apiFetch<{ user: User }>("/auth/me");
}

export async function logout() {
  return apiFetch<void>("/auth/logout", { method: "POST" });
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