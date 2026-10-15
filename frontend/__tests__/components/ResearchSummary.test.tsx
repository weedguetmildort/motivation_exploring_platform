import { render, screen } from "@testing-library/react";
import ResearchSummary from "../../components/ResearchSummary";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));

test("distinguishes unavailable rates from zero and shows opportunity denominators", async () => {
  (apiFetch as jest.Mock).mockResolvedValue({ variants: [{
    participant_id: "participant", attempt_id: "attempt", quiz_id: "links", attempt_status: "completed",
    questions_assigned: 5, questions_answered: 5, accuracy: 0.8, wrong_ai_exposure_questions: 0,
    wrong_ai_agreement_rate: null, telemetry_questions: 4, questions_with_quality_flags: 1,
    median_active_ms: 12000, suggestion_click_rate: null, reference_click_rate: 0,
  }] });
  render(<ResearchSummary />);
  expect(await screen.findByText("participant")).toBeInTheDocument();
  expect(screen.getByText("80.0%")).toBeInTheDocument();
  expect(screen.getByText("0.0%")).toBeInTheDocument();
  expect(screen.getAllByText("—")).toHaveLength(2);
  expect(screen.getByText("4/5")).toBeInTheDocument();
  expect(screen.getByText(/does not establish that AI changed/)).toBeInTheDocument();
});
