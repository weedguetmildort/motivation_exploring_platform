import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import AllowlistPanelPage from "../../pages/allowlist_panel";
import { getMe, logout } from "../../lib/auth";
import { apiFetch } from "../../lib/fetcher";

const mockReplace = jest.fn();
const mockPush = jest.fn();
jest.mock("next/router", () => ({
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
}));

jest.mock("../../lib/auth", () => ({
  getMe: jest.fn(),
  logout: jest.fn(),
}));

jest.mock("../../lib/fetcher", () => ({
  apiFetch: jest.fn(),
}));

const mockGetMe = getMe as jest.Mock;
const mockLogout = logout as jest.Mock;
const mockApiFetch = apiFetch as jest.Mock;

const adminUser = { id: "1", email: "admin@example.com", is_admin: true };

const entry1 = {
  id: "entry1",
  domain: "khanacademy.org",
  added_by: "admin@example.com",
  added_at: "2024-01-01T00:00:00.000Z",
};

const entry2 = {
  id: "entry2",
  domain: "stanford.edu",
  added_by: "owner@example.com",
  added_at: "2024-02-01T00:00:00.000Z",
};

describe("AllowlistPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<AllowlistPanelPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<AllowlistPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Trusted Domain Allowlist")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<AllowlistPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the panel and loads allowlist entries for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([entry1, entry2]);
    render(<AllowlistPanelPage />);

    expect(await screen.findByText("Trusted Domain Allowlist")).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("khanacademy.org")).toBeInTheDocument();
    expect(within(table).getByText("stanford.edu")).toBeInTheDocument();
    expect(within(table).getByText("admin@example.com")).toBeInTheDocument();
    expect(within(table).getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("(2)")).toBeInTheDocument();
  });

  it("shows a message when there are no allowlist entries", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);

    await screen.findByText("Trusted Domain Allowlist");
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/allowlist"));

    expect(await screen.findByText("No domains in the allowlist yet. Add one above.")).toBeInTheDocument();
  });

  it("shows an error message when loading the allowlist fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<AllowlistPanelPage />);

    expect(await screen.findByText("Failed to load allowlist.")).toBeInTheDocument();
  });

  it("disables the add button until a domain is entered", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const addButton = screen.getByRole("button", { name: "Add domain" });
    expect(addButton).toBeDisabled();

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "khanacademy.org" } });

    expect(addButton).not.toBeDisabled();
  });

  it("shows an error for an invalid bare domain", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "not a domain" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));

    expect(
      await screen.findByText('"not a domain" is not a valid bare domain (e.g. khanacademy.org).'),
    ).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/allowlist", expect.objectContaining({ method: "POST" }));
  });

  it("normalizes scheme, www, path, and port before validating", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = { id: "entry3", domain: "khanacademy.org", added_by: "admin@example.com", added_at: "2024-03-01T00:00:00.000Z" };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "HTTPS://www.khanacademy.org:8080/resource/path?x=1" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/allowlist",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ domain: "khanacademy.org" }),
        }),
      ),
    );

    expect(await screen.findByText("Added: khanacademy.org")).toBeInTheDocument();
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("shows an error when the domain is already in the allowlist (client-side check)", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([entry1]);
    render(<AllowlistPanelPage />);
    await screen.findByText("khanacademy.org");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "khanacademy.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));

    expect(await screen.findByText("This domain is already in the allowlist.")).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/allowlist", expect.objectContaining({ method: "POST" }));
  });

  it("shows a duplicate error when the server responds with a 409", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.reject(new Error("Request failed with status 409"));
      return Promise.resolve(undefined);
    });

    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "khanacademy.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));

    expect(await screen.findByText("This domain is already in the allowlist.")).toBeInTheDocument();
  });

  it("shows a generic error when adding a domain fails for another reason", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "khanacademy.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));

    expect(await screen.findByText("Failed to add domain.")).toBeInTheDocument();
  });

  it("clears previous error and success messages when typing", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);
    await screen.findByText("No domains in the allowlist yet. Add one above.");

    const input = screen.getByPlaceholderText("khanacademy.org");
    fireEvent.change(input, { target: { value: "not a domain" } });
    fireEvent.click(screen.getByRole("button", { name: "Add domain" }));
    expect(await screen.findByText(/is not a valid bare domain/)).toBeInTheDocument();

    fireEvent.change(input, { target: { value: "khanacademy.org" } });
    expect(screen.queryByText(/is not a valid bare domain/)).not.toBeInTheDocument();
  });

  it("removes a domain after confirmation", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([entry1]);
      if (method === "DELETE") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<AllowlistPanelPage />);
    await screen.findByRole("button", { name: "Remove" });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/allowlist/entry1", expect.objectContaining({ method: "DELETE" })),
    );
    expect(await screen.findByText("No domains in the allowlist yet. Add one above.")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("does not remove a domain when confirmation is cancelled", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([entry1]);

    render(<AllowlistPanelPage />);
    await screen.findByRole("button", { name: "Remove" });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/allowlist/entry1", expect.anything());
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an alert when removing a domain fails", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([entry1]);
      if (method === "DELETE") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<AllowlistPanelPage />);
    await screen.findByRole("button", { name: "Remove" });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to remove domain."));

    confirmSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it("navigates to the dashboard when Back to Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);

    fireEvent.click(await screen.findByText("Back to Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<AllowlistPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
