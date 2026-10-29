import { fireEvent, render, screen } from "@testing-library/react";
import StudyAccessCodeAdmin from "../../components/StudyAccessCodeAdmin";
import { apiFetch } from "../../lib/fetcher";
jest.mock("../../lib/fetcher", () => ({ apiFetch: jest.fn() }));
beforeEach(() => (apiFetch as jest.Mock).mockReset());

const stored = { code: "ABCD-EFGH", version: 1, rotated_at: "2026-10-26T12:00:00Z", rotated_by: "admin" };

test("generates the first access code without confirmation", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(url.endsWith("/rotate")
    ? stored : { code: null, version: 0, rotated_at: null, rotated_by: null }));
  render(<StudyAccessCodeAdmin />);
  expect(await screen.findByText(/No access code yet/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Generate access code" }));
  expect(await screen.findByLabelText("Current access code")).toHaveTextContent("ABCD-EFGH");
  expect(apiFetch).toHaveBeenCalledWith("/api/studies/access-code/rotate", { method: "POST" });
});

test("rotation requires confirmation and can be cancelled", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => Promise.resolve(url.endsWith("/rotate")
    ? { ...stored, code: "JKLM-NPQR", version: 2 } : stored));
  render(<StudyAccessCodeAdmin />);
  fireEvent.click(await screen.findByRole("button", { name: "Rotate access code" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(apiFetch).not.toHaveBeenCalledWith("/api/studies/access-code/rotate", expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "Rotate access code" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm rotation" }));
  expect(await screen.findByLabelText("Current access code")).toHaveTextContent("JKLM-NPQR");
  expect(screen.getByText(/Version 2/)).toBeInTheDocument();
});

test("shows load errors", async () => {
  (apiFetch as jest.Mock).mockRejectedValue(new Error("Admin access required"));
  render(<StudyAccessCodeAdmin />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Admin access required");
});

test("a failed load can be retried without reloading the page", async () => {
  (apiFetch as jest.Mock).mockRejectedValueOnce(new Error("Network unavailable")).mockResolvedValueOnce(stored);
  render(<StudyAccessCodeAdmin />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
  expect(screen.getByRole("button", { name: "Generate access code" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByLabelText("Current access code")).toHaveTextContent("ABCD-EFGH");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledTimes(2);
});

test("a retry that finds no code yet offers to generate one", async () => {
  (apiFetch as jest.Mock).mockRejectedValueOnce(new Error("Network unavailable"))
    .mockResolvedValueOnce({ code: null, version: 0, rotated_at: null, rotated_by: null });
  render(<StudyAccessCodeAdmin />);
  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
  expect(await screen.findByText(/No access code yet/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Generate access code" })).toBeEnabled();
});

test("a failed rotation is not offered as a reload", async () => {
  (apiFetch as jest.Mock).mockImplementation((url: string) => url.endsWith("/rotate")
    ? Promise.reject(new Error("Rotation failed")) : Promise.resolve(stored));
  render(<StudyAccessCodeAdmin />);
  fireEvent.click(await screen.findByRole("button", { name: "Rotate access code" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm rotation" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Rotation failed");
  expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Current access code")).toHaveTextContent("ABCD-EFGH");
});
