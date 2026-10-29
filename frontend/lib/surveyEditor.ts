import type { SurveyItem, SurveyOption, SurveyScale } from "./surveys";
import { questionTarget, targetFields } from "./surveyConfig";

export type SurveyDraft = Omit<SurveyItem, "id" | "type"> & {
  type: "likert" | "single_select"; required: boolean; active: boolean;
  category: string; reverse_scored: boolean; order: number; scale: SurveyScale; options: SurveyOption[];
};

export function surveyDraft(item?: SurveyItem): SurveyDraft {
  return { stage: "pre_quiz", prompt: "", type: "likert", required: true, active: true,
    reverse_scored: false, order: 0, ...item, category: item?.category ?? "",
    scale: item?.scale ?? { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] },
    options: item?.options ?? ["a", "b", "c", "d", "e"].map(id => ({ id, label: "" })),
  } as SurveyDraft;
}

export function surveyItemPayload(draft: SurveyDraft) {
  if (!draft.prompt.trim()) throw new Error("Prompt is required.");
  const common = { ...targetFields(questionTarget(draft), draft.stages),
    category: draft.category.trim() || null, prompt: draft.prompt.trim(), type: draft.type,
    required: draft.required, reverse_scored: draft.reverse_scored, order: draft.order, active: draft.active };
  if (draft.type === "likert") {
    if (draft.scale.min >= draft.scale.max) throw new Error("Likert scale min must be less than max.");
    return { ...common, options: null, scale: { min: draft.scale.min, max: draft.scale.max,
      anchors: [draft.scale.anchors?.[0] || "Strongly disagree", draft.scale.anchors?.[1] || "Strongly agree"] } };
  }
  const options = draft.options.map(option => ({ ...option, label: option.label.trim() })).filter(option => option.label);
  if (options.length < 2) throw new Error("Single-select requires at least 2 options.");
  return { ...common, scale: null, options };
}
