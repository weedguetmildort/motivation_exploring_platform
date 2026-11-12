import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import NewParticipantSettings from "../../components/NewParticipantSettings";
import { apiFetch } from "../../lib/fetcher";

jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
const mockApiFetch = apiFetch as jest.Mock;

function api(next = { next: "double", source: "override" }, sets: string[] | null = ["a"]) {
  mockApiFetch.mockImplementation((url: string, init?: { method?: string; body?: string }) => {
    if (url.endsWith("next-assignment")) {
      if (init?.method === "PUT") {
        const variant = JSON.parse(init.body!).variant;
        return Promise.resolve(variant ? { next: variant, source: "override" } : { next: "followup", source: "rotation" });
      }
      return Promise.resolve(next);
    }
    if (init?.method === "PUT") return Promise.resolve({ sets: JSON.parse(init.body!).sets });
    return Promise.resolve({ sets });
  });
}

beforeEach(() => mockApiFetch.mockReset());

test("reads and writes the study it is given", async () => {
  api();
  render(<NewParticipantSettings study="study-2" />);
  const group = within(screen.getByRole("group", { name: "Next sign-up" }));
  expect(await group.findByText("Dual-Agent")).toBeInTheDocument();
  expect(group.getByText("(override)")).toBeInTheDocument();
  expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-2/users/next-assignment");
  expect(mockApiFetch).not.toHaveBeenCalledWith("/api/studies/study-2/users/quiz-default-sets");
  fireEvent.click(group.getByRole("button", { name: "Reset to rotation" }));
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-2/users/next-assignment",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ variant: null }) })));
  expect(await group.findByText("(rotation)")).toBeInTheDocument();
});

test("Study 1 shows its default question sets and reports changes", async () => {
  api();
  const onChange = jest.fn();
  render(<NewParticipantSettings study="study-1" onDefaultSetsChange={onChange} />);
  const group = within(screen.getByRole("group", { name: "Default question sets" }));
  await waitFor(() => expect(group.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "true"));
  expect(onChange).toHaveBeenLastCalledWith(["a"]);
  fireEvent.click(group.getByRole("button", { name: "C" }));
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-1/users/quiz-default-sets",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ sets: ["a", "c"] }) })));
  expect(onChange).toHaveBeenLastCalledWith(["a", "c"]);
});

test("clearing every default set sends no restriction", async () => {
  api(undefined, ["b"]);
  render(<NewParticipantSettings study="study-1" />);
  const group = within(screen.getByRole("group", { name: "Default question sets" }));
  await waitFor(() => expect(group.getByRole("button", { name: "B" })).toHaveAttribute("aria-pressed", "true"));
  fireEvent.click(group.getByRole("button", { name: "B" }));
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-1/users/quiz-default-sets",
    expect.objectContaining({ body: JSON.stringify({ sets: null }) })));
});

test("a failed default-set save rolls back and says so", async () => {
  api();
  const onChange = jest.fn();
  render(<NewParticipantSettings study="study-1" onDefaultSetsChange={onChange} />);
  const group = within(screen.getByRole("group", { name: "Default question sets" }));
  await waitFor(() => expect(group.getByRole("button", { name: "A" })).toHaveAttribute("aria-pressed", "true"));
  mockApiFetch.mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(group.getByRole("button", { name: "D" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Failed to update the default question sets.");
  expect(group.getByRole("button", { name: "D" })).toHaveAttribute("aria-pressed", "false");
  expect(onChange).toHaveBeenLastCalledWith(["a"]);
});

test("a failed next sign-up change is reported", async () => {
  api();
  render(<NewParticipantSettings study="study-1" />);
  const group = within(screen.getByRole("group", { name: "Next sign-up" }));
  await group.findByText("(override)");
  mockApiFetch.mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(group.getByRole("button", { name: "Set Links" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Failed to update the next sign-up.");
});

test("a failed load leaves the section usable", async () => {
  mockApiFetch.mockRejectedValue(new Error("offline"));
  render(<NewParticipantSettings study="study-1" />);
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2));
  expect(screen.getByRole("button", { name: "Set Links" })).toBeEnabled();
  expect(screen.queryByText(/\(rotation\)|\(override\)/)).not.toBeInTheDocument();
});

test("switching study reloads that study's settings", async () => {
  api();
  const { rerender } = render(<NewParticipantSettings study="study-1" />);
  await screen.findByRole("group", { name: "Default question sets" });
  rerender(<NewParticipantSettings study="study-2" />);
  await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/studies/study-2/users/next-assignment"));
  expect(screen.queryByRole("group", { name: "Default question sets" })).not.toBeInTheDocument();
});
