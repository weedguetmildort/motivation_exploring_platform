export type StudyId = "study-1" | "study-2";

export type StudyAccessPolicy = {
  mode: "sequential_approval" | "sequential" | "independent_approval" | "independent";
  requires_study1_completion: boolean;
  requires_approval: boolean;
};
export const DEFAULT_ACCESS_POLICY: StudyAccessPolicy = {
  mode: "sequential_approval", requires_study1_completion: true, requires_approval: true,
};

export function rememberStudy(study: StudyId) {
  try { sessionStorage.setItem("mep.selectedStudy", study); } catch { /* Explicit URLs still work without storage. */ }
}

export function selectedStudy(): StudyId {
  if (typeof window === "undefined") return "study-1";
  const requested = new URLSearchParams(window.location.search).get("study");
  if (requested === "study-1" || requested === "study-2") return requested;
  try { return sessionStorage.getItem("mep.selectedStudy") === "study-2" ? "study-2" : "study-1"; }
  catch { return "study-1"; }
}

export function studyApiPath(input: RequestInfo | URL, study: StudyId = selectedStudy()): RequestInfo | URL {
  if (typeof input !== "string" || study === "study-1") return input;
  if (input.startsWith("/api/studies/study-") || input.startsWith("/api/studies/catalog") || input.startsWith("/api/studies/participants") || input.startsWith("/api/studies/access-code")) return input;
  if (["/auth/login", "/auth/signup", "/auth/logout", "/auth/change-password"].includes(input)) return input;
  if (input.startsWith("/api/")) return `/api/studies/${study}/${input.slice(5)}`;
  if (input.startsWith("/auth/")) return `/api/studies/${study}${input}`;
  return input;
}

export function studyPageUrl(path: string, study: StudyId = selectedStudy()) {
  if (!path.startsWith("/") || path.startsWith("//")) return path;
  const url = new URL(path, "http://study.local");
  if (["/login", "/signup", "/"].includes(url.pathname)) return path;
  if (!url.searchParams.has("study")) url.searchParams.set("study", study);
  return `${url.pathname}${url.search}${url.hash}`;
}
