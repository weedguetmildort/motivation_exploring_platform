import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import LinkPanelPage from "../../pages/links_panel";
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

const readyLink = {
  id: "link1",
  title: "Khan Academy Probability",
  url: "https://khanacademy.org/probability",
  tags: ["Basic Probability"],
  description: "Intro to probability",
  status: "READY" as const,
};

const reviewLink = {
  id: "link2",
  title: "New Discovery",
  url: "https://example.com/new",
  tags: ["Combinatorics & Counting"],
  description: "Discovered link",
  status: "NEEDS_REVIEW" as const,
};

const deadLink = {
  id: "link3",
  title: "Dead Link",
  url: "https://example.com/dead",
  tags: ["Other"],
  description: "This link is dead",
  status: "NOT_READY" as const,
  last_checked: "2024-01-01T00:00:00.000Z",
  last_http_code: 404,
  last_error_type: "http_error",
};

const rejectedLink = {
  id: "link4",
  title: "Rejected Link",
  url: "https://example.com/rejected",
  tags: ["Other"],
  description: "Rejected",
  status: "REJECTED" as const,
};

describe("LinkPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<LinkPanelPage />);
    expect(screen.getByText("Loading admin links panel…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<LinkPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Knowledge Links Panel")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<LinkPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the panel and loads links for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);
    render(<LinkPanelPage />);

    expect(await screen.findByText("Knowledge Links Panel")).toBeInTheDocument();
    expect(await screen.findByText("Khan Academy Probability")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Intro to probability")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: readyLink.url })).toHaveAttribute("href", readyLink.url);
  });

  it("shows a message when there are no links", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<LinkPanelPage />);

    await screen.findByText("Knowledge Links Panel");
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/knowledge-links"));

    expect(await screen.findByText("No knowledge links yet.")).toBeInTheDocument();
  });

  it("shows an error message when loading links fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<LinkPanelPage />);

    expect(await screen.findByText("Failed to load knowledge links.")).toBeInTheDocument();
  });

  it("validates the create-link form step by step", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);
    const { container } = render(<LinkPanelPage />);

    await screen.findByText("Khan Academy Probability");

    const form = container.querySelector("form")!;
    const [titleInput, urlInput, descriptionInput] = screen.getAllByRole("textbox");

    fireEvent.submit(form);
    expect(await screen.findByText("Title is required.")).toBeInTheDocument();

    fireEvent.change(titleInput, { target: { value: "New Resource" } });
    fireEvent.submit(form);
    expect(await screen.findByText("URL is required.")).toBeInTheDocument();

    fireEvent.change(urlInput, { target: { value: "not-a-url" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Please enter a valid URL.")).toBeInTheDocument();

    fireEvent.change(urlInput, { target: { value: readyLink.url } });
    fireEvent.submit(form);
    expect(await screen.findByText(/This URL is already in the database/)).toBeInTheDocument();

    fireEvent.change(urlInput, { target: { value: "https://example.com/unique" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Description is required.")).toBeInTheDocument();

    fireEvent.change(descriptionInput, { target: { value: "A description" } });
    fireEvent.submit(form);
    expect(await screen.findByText("Please select a tag.")).toBeInTheDocument();

    expect(mockApiFetch).not.toHaveBeenCalledWith(
      "/api/knowledge-links",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows hints for duplicate and unique URLs", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);
    render(<LinkPanelPage />);

    await screen.findByText("Khan Academy Probability");

    const urlInput = screen.getAllByRole("textbox")[1];
    fireEvent.change(urlInput, { target: { value: readyLink.url } });
    expect(await screen.findByText("Link already in the database")).toBeInTheDocument();

    fireEvent.change(urlInput, { target: { value: "https://example.com/unique" } });
    expect(await screen.findByText("New link")).toBeInTheDocument();
  });

  it("creates a new knowledge link and resets the form", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = {
      id: "link5",
      title: "New Resource",
      url: "https://example.com/new-resource",
      tags: ["Basic Probability"],
      description: "A description",
      status: "READY" as const,
    };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST" && url === "/api/knowledge-links") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("No knowledge links yet.");

    const [titleInput, urlInput, descriptionInput] = screen.getAllByRole("textbox");
    fireEvent.change(titleInput, { target: { value: "New Resource" } });
    fireEvent.change(urlInput, { target: { value: "https://example.com/new-resource" } });
    fireEvent.change(descriptionInput, { target: { value: "A description" } });
    fireEvent.click(screen.getByRole("button", { name: "Basic Probability" }));

    fireEvent.click(screen.getByRole("button", { name: "Save knowledge link" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/knowledge-links",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            title: "New Resource",
            url: "https://example.com/new-resource",
            description: "A description",
            tags: ["Basic Probability"],
          }),
        }),
      ),
    );

    expect(await screen.findByText("Knowledge link added.")).toBeInTheDocument();
    expect((titleInput as HTMLInputElement).value).toBe("");
    expect(await screen.findByText("New Resource")).toBeInTheDocument();
  });

  it("shows an error message when creating a link fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("No knowledge links yet.");

    const [titleInput, urlInput, descriptionInput] = screen.getAllByRole("textbox");
    fireEvent.change(titleInput, { target: { value: "New Resource" } });
    fireEvent.change(urlInput, { target: { value: "https://example.com/new-resource" } });
    fireEvent.change(descriptionInput, { target: { value: "A description" } });
    fireEvent.click(screen.getByRole("button", { name: "Basic Probability" }));

    fireEvent.click(screen.getByRole("button", { name: "Save knowledge link" }));

    expect(await screen.findByText("Failed to add knowledge link.")).toBeInTheDocument();
  });

  it("clears the form when Clear form is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<LinkPanelPage />);
    await screen.findByText("No knowledge links yet.");

    const [titleInput, urlInput, descriptionInput] = screen.getAllByRole("textbox");
    fireEvent.change(titleInput, { target: { value: "Something" } });
    fireEvent.change(urlInput, { target: { value: "https://example.com/x" } });
    fireEvent.change(descriptionInput, { target: { value: "Desc" } });
    fireEvent.click(screen.getByRole("button", { name: "Basic Probability" }));

    fireEvent.click(screen.getByRole("button", { name: "Clear form" }));

    expect((titleInput as HTMLInputElement).value).toBe("");
    expect((urlInput as HTMLInputElement).value).toBe("");
    expect((descriptionInput as HTMLTextAreaElement).value).toBe("");
  });

  it("filters links by tab", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink, reviewLink, deadLink, rejectedLink]);
    render(<LinkPanelPage />);

    await screen.findByText("Khan Academy Probability");

    expect(screen.getByRole("button", { name: "All (4)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review Queue (1)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dead Links (1)" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Review Queue (1)" }));
    expect(screen.getByText("New Discovery")).toBeInTheDocument();
    expect(screen.queryByText("Khan Academy Probability")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dead Links (1)" }));
    expect(screen.getByText("Dead Link")).toBeInTheDocument();
    expect(screen.queryByText("New Discovery")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All (4)" }));
    expect(screen.getByText("Khan Academy Probability")).toBeInTheDocument();
    expect(screen.getByText("New Discovery")).toBeInTheDocument();
    expect(screen.getByText("Dead Link")).toBeInTheDocument();
    expect(screen.getByText("Rejected Link")).toBeInTheDocument();
  });

  it("shows tab-specific empty messages", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);
    render(<LinkPanelPage />);

    await screen.findByText("Khan Academy Probability");

    fireEvent.click(screen.getByRole("button", { name: "Review Queue" }));
    expect(await screen.findByText("No links awaiting review.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dead Links" }));
    expect(await screen.findByText("No dead links.")).toBeInTheDocument();
  });

  it("approves a link awaiting review", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const approved = { ...reviewLink, status: "READY" as const };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([reviewLink]);
      if (method === "POST" && url === "/api/knowledge-links/link2/approve") return Promise.resolve(approved);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("New Discovery");

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/knowledge-links/link2/approve",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("Ready")).toBeInTheDocument();
  });

  it("rejects a link awaiting review after confirmation", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    mockGetMe.mockResolvedValue({ user: adminUser });
    const rejected = { ...reviewLink, status: "REJECTED" as const };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([reviewLink]);
      if (method === "POST" && url === "/api/knowledge-links/link2/reject") return Promise.resolve(rejected);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("New Discovery");

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/knowledge-links/link2/reject",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("Tombstoned")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("does not reject a link when confirmation is cancelled", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([reviewLink]);

    render(<LinkPanelPage />);
    await screen.findByText("New Discovery");

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/knowledge-links/link2/reject", expect.anything());
    expect(screen.getByText("New Discovery")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an alert when approving a link fails", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([reviewLink]);
      if (method === "POST" && url === "/api/knowledge-links/link2/approve") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("New Discovery");

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to approve link."));
    alertSpy.mockRestore();
  });

  it("shows an alert when rejecting a link fails", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([reviewLink]);
      if (method === "POST" && url === "/api/knowledge-links/link2/reject") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("New Discovery");

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to reject link."));

    confirmSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it("shows health check metadata for a dead link", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([deadLink]);
    render(<LinkPanelPage />);

    await screen.findByText("Dead Link");
    expect(screen.getByText("Not Ready")).toBeInTheDocument();
    expect(screen.getByText(/HTTP 404/)).toBeInTheDocument();
    expect(screen.getByText(/HTTP error/)).toBeInTheDocument();
  });

  it("deletes a dead link after confirmation", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([deadLink]);
      if (method === "DELETE") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("Dead Link");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/knowledge-links/link3", expect.objectContaining({ method: "DELETE" })),
    );
    await waitFor(() => expect(screen.queryByText("Dead Link")).not.toBeInTheDocument());

    confirmSpy.mockRestore();
  });

  it("does not delete a dead link when confirmation is cancelled", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([deadLink]);

    render(<LinkPanelPage />);
    await screen.findByText("Dead Link");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/knowledge-links/link3", expect.anything());
    expect(screen.getByText("Dead Link")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an alert when deleting a link fails", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([deadLink]);
      if (method === "DELETE") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("Dead Link");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to delete knowledge link."));

    confirmSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it("edits a ready link and saves changes", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const updated = {
      ...readyLink,
      title: "Updated Title",
      url: "https://example.com/updated",
      description: "Updated description",
      tags: ["Other"],
    };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([readyLink]);
      if (method === "PUT") return Promise.resolve(updated);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("Khan Academy Probability");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const textboxes = screen.getAllByRole("textbox");
    const editTitle = textboxes[3];
    const editUrl = textboxes[4];
    const editDescription = textboxes[5];

    fireEvent.change(editTitle, { target: { value: "Updated Title" } });
    fireEvent.change(editUrl, { target: { value: "https://example.com/updated" } });
    fireEvent.change(editDescription, { target: { value: "Updated description" } });

    const otherButtons = screen.getAllByRole("button", { name: "Other" });
    fireEvent.click(otherButtons[otherButtons.length - 1]);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/knowledge-links/link1",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            title: "Updated Title",
            url: "https://example.com/updated",
            description: "Updated description",
            tags: ["Other"],
          }),
        }),
      ),
    );

    expect(await screen.findByText("Updated Title")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("cancels editing a link without saving", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);

    render(<LinkPanelPage />);
    await screen.findByText("Khan Academy Probability");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.getByText("Khan Academy Probability")).toBeInTheDocument();
  });

  it("validates the edit form before saving", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([readyLink]);

    render(<LinkPanelPage />);
    await screen.findByText("Khan Academy Probability");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const textboxes = screen.getAllByRole("textbox");
    const editTitle = textboxes[3];
    const editUrl = textboxes[4];
    const editDescription = textboxes[5];

    fireEvent.change(editTitle, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(alertSpy).toHaveBeenCalledWith("Title is required.");

    fireEvent.change(editTitle, { target: { value: "Valid title" } });
    fireEvent.change(editUrl, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(alertSpy).toHaveBeenCalledWith("URL is required.");

    fireEvent.change(editUrl, { target: { value: "not-a-url" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(alertSpy).toHaveBeenCalledWith("Please enter a valid URL.");

    fireEvent.change(editUrl, { target: { value: "https://example.com/valid" } });
    fireEvent.change(editDescription, { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(alertSpy).toHaveBeenCalledWith("Description is required.");

    fireEvent.change(editDescription, { target: { value: "Valid description" } });
    const tagButtons = screen.getAllByRole("button", { name: "Basic Probability" });
    fireEvent.click(tagButtons[tagButtons.length - 1]);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(alertSpy).toHaveBeenCalledWith("Please select a tag.");

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/knowledge-links/link1", expect.objectContaining({ method: "PUT" }));

    alertSpy.mockRestore();
  });

  it("shows an alert when saving an edited link fails", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([readyLink]);
      if (method === "PUT") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("Khan Academy Probability");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to update knowledge link."));
    alertSpy.mockRestore();
  });

  it("triggers a health check", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST" && url === "/api/knowledge-links/trigger-health-check") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("No knowledge links yet.");

    fireEvent.click(screen.getByRole("button", { name: "Trigger Health Check" }));

    expect(
      await screen.findByText("Health check triggered. Refresh in a moment to see updated statuses."),
    ).toBeInTheDocument();
  });

  it("shows an error message when triggering a health check fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST" && url === "/api/knowledge-links/trigger-health-check") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<LinkPanelPage />);
    await screen.findByText("No knowledge links yet.");

    fireEvent.click(screen.getByRole("button", { name: "Trigger Health Check" }));

    expect(await screen.findByText("Failed to trigger health check.")).toBeInTheDocument();
  });

  it("navigates to the dashboard when Back to Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<LinkPanelPage />);

    fireEvent.click(await screen.findByText("Back to Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<LinkPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
