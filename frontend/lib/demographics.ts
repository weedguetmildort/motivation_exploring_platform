import { apiFetch } from "./fetcher";

export type DemographicsPayload = {
  gender: string;
  other_gender?: string,
  race_ethnicity: string[],
  year: string;
  major?: string;
};

export async function saveMyDemographics(payload: DemographicsPayload) {
  return apiFetch<{ ok: boolean }>("/api/demographics/me", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
