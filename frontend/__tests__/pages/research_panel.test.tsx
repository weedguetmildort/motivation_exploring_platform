import { render, screen, waitFor } from "@testing-library/react";
import ResearchPanel from "../../pages/research_panel";
import { getMe } from "../../lib/auth";
const replace = jest.fn();
jest.mock("next/router", () => ({ useRouter: () => ({ replace, push: jest.fn() }) }));
jest.mock("../../lib/auth", () => ({ getMe: jest.fn(), logout: jest.fn() }));
jest.mock("../../components/ResearchSummary", () => ({ __esModule: true, default: () => <div>Filtered research dashboard</div> }));
beforeEach(() => { replace.mockReset(); });
test("shows the research dashboard for administrators", async () => {
  (getMe as jest.Mock).mockResolvedValue({ user: { is_admin: true } });
  render(<ResearchPanel />);
  expect(await screen.findByText("Filtered research dashboard")).toBeInTheDocument();
});
test("does not mount the dashboard for participants", async () => {
  (getMe as jest.Mock).mockResolvedValue({ user: { is_admin: false } });
  render(<ResearchPanel />);
  await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  expect(screen.queryByText("Filtered research dashboard")).not.toBeInTheDocument();
});
