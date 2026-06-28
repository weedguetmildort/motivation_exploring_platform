// frontend/lib/demographics.ts
import { apiFetch } from "./fetcher";

export type DemographicsPayload = {
  gender: string;
  other_gender?: string;
  race_ethnicity: string[];
  year: string;
  academic_level: string;
  other_academic_level?: string;
  major?: string;
  other_major?: string;
  class_name?: string;
  age: string;
};

export async function saveMyDemographics(payload: DemographicsPayload) {
  return apiFetch<{ ok: boolean }>("/api/demographics/me", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
