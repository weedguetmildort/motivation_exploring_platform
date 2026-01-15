// Auth client: talks to backend via relative URLs, relying on Next.js rewrites
// Endpoints expected:
//   POST /auth/signup { email, password } -> 200 + sets cookie
//   POST /auth/login  { email, password } -> 200 + sets cookie
//   POST /auth/logout {}                 -> 204 (optional, if you add it)
//   GET  /auth/me                        -> 200 { user } if authenticated

import { apiFetch } from "./fetcher";

export type User = {
  id: string;
  email: string;
  is_admin: boolean;
  demographics_completed?: boolean;
  quiz_pre_survey_completed?: boolean;
};

export async function signup(email: string, password: string) {
  return apiFetch<{ user: User }>("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string) {
  return apiFetch<{ user: User }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe() {
  // Throws if not authenticated
  return apiFetch<{ user: User }>("/auth/me");
}

export async function logout() {
  // If you implement it on the backend
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