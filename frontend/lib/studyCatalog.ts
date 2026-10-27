import { apiFetch } from "./fetcher";
import type { StudyAccessPolicy } from "./studySelection";
import type { Enrollment } from "../components/StudyShell";

export type StudyCatalog = { studies: Enrollment[]; access_policy?: StudyAccessPolicy };

// StudyShell loads the catalog before rendering the dashboard, which loads it
// again, and both poll every 15 s. Reuse a result this fresh instead of asking
// twice. Anything that changes access must call invalidateStudyCatalog().
const REUSE_MS = 2000;
let inFlight: Promise<StudyCatalog> | null = null;
let last: { at: number; value: StudyCatalog } | null = null;

export function fetchStudyCatalog(): Promise<StudyCatalog> {
  if (last && Date.now() - last.at < REUSE_MS) return Promise.resolve(last.value);
  if (!inFlight) {
    const request = apiFetch<StudyCatalog>("/api/studies/catalog");
    inFlight = request;
    request.then(value => { if (inFlight === request) last = { at: Date.now(), value }; }, () => {})
      .finally(() => { if (inFlight === request) inFlight = null; });
  }
  return inFlight;
}

export function invalidateStudyCatalog() {
  last = null;
  inFlight = null;
}
