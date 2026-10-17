import type { SurveyStages } from "./study";

export const DEFAULT_SURVEY_STAGES: SurveyStages = {
  pre_quiz: { name: "Pre-Quiz Survey", enabled: true },
  post_base: { name: "Post-Base Quiz Survey", enabled: true },
  post_followup: { name: "Post-Follow-up Questions Survey", enabled: true },
  post_double: { name: "Post-Dual Agent Survey", enabled: true },
  post_links: { name: "Post-Embedded Links Survey", enabled: true },
};

export type QuestionScope = "all_surveys" | "post_quiz" | "stages";
export type TargetedQuestion = { stage: string; scope?: QuestionScope | null; stages?: string[]; active?: boolean };
export function questionApplies(item: TargetedQuestion, stage: string): boolean {
  if (item.active === false) return false;
  if (item.scope === "all_surveys") return true;
  if (item.scope === "post_quiz") return stage !== "pre_quiz";
  if (item.scope === "stages") return item.stages?.includes(stage) ?? false;
  return item.stage === stage || (item.stage === "post_base" && stage !== "pre_quiz");
}

export function questionTarget(item: TargetedQuestion): string {
  return item.scope === "all_surveys" || item.scope === "post_quiz" ? item.scope :
    item.scope === "stages" ? item.stages?.[0] ?? item.stage : item.stage === "post_base" || item.stage === "post_variant" ? "post_quiz" : item.stage;
}

export function targetFields(target: string, stages: string[] = []) {
  if (target === "all_surveys" || target === "post_quiz") return { stage: target === "all_surveys" ? "pre_quiz" : "post_base", scope: target, stages: [] };
  const targets = [...new Set([target, ...stages])];
  return { stage: target, scope: "stages", stages: targets };
}
