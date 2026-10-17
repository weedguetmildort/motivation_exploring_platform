import { render, screen, fireEvent } from "@testing-library/react";
import SurveyTimeline from "../../components/SurveyTimeline";
import { DEFAULT_SURVEY_STAGES } from "../../lib/surveyConfig";

test("can disable initial, final and intermediate stages and edit admin names", () => {
  const change = jest.fn();
  render(<SurveyTimeline stages={DEFAULT_SURVEY_STAGES} onChange={change} />);
  fireEvent.click(screen.getByRole("button", { name: "Disable all" }));
  expect(Object.values(change.mock.calls[0][0]).every((v: any) => !v.enabled)).toBe(true);
  fireEvent.click(screen.getByLabelText("Enable pre_quiz"));
  expect(change.mock.calls[1][0].pre_quiz.enabled).toBe(false);
  fireEvent.change(screen.getByLabelText("Admin name for post_links"), { target: { value: "Reference verification" } });
  expect(change.mock.calls[2][0].post_links.name).toBe("Reference verification");
  fireEvent.click(screen.getByRole("button", { name: "Enable all" }));
  expect(Object.values(change.mock.calls[3][0]).every((v: any) => v.enabled)).toBe(true);
  expect(screen.getAllByRole("link", { name: "Edit questions" })[0]).toHaveAttribute("href", expect.stringContaining("stage=pre_quiz"));
});
