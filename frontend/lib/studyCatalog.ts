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
// Bumped on every invalidation, so a request sent before an access change
// (or by the previous account) never answers a caller after it.
let generation = 0;

export function fetchStudyCatalog(): Promise<StudyCatalog> {
  if (last && Date.now() - last.at < REUSE_MS) return Promise.resolve(last.value);
  if (!inFlight) {
    const started = generation;
    const request: Promise<StudyCatalog> = apiFetch<StudyCatalog>("/api/studies/catalog").then(value => {
      if (started !== generation) return fetchStudyCatalog();
      last = { at: Date.now(), value };
      return value;
    });
    inFlight = request;
    request.finally(() => { if (inFlight === request) inFlight = null; }).catch(() => {});
  }
  return inFlight;
}

export function invalidateStudyCatalog() {
  generation += 1;
  last = null;
  inFlight = null;
}
