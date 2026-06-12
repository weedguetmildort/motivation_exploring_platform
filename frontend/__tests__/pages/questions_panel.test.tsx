import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import QuestionPanelPage from "../../pages/questions_panel";
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

const question1 = {
  id: "q1",
  stem: "What is 2+2?",
  subtitle: "Basic arithmetic",
  choices: [
    { id: "a", label: "3" },
    { id: "b", label: "4" },
    { id: "c", label: "5" },
    { id: "d", label: "6" },
  ],
  correct_choice_id: "b",
};

describe("QuestionPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<QuestionPanelPage />);
    expect(screen.getByText("Loading quiz questions panel…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<QuestionPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Quiz Questions Panel")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<QuestionPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the panel and loads questions for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([question1]);
    render(<QuestionPanelPage />);

    expect(await screen.findByText("Quiz Questions Panel")).toBeInTheDocument();
    expect(await screen.findByText("What is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("Basic arithmetic")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("(correct)")).toBeInTheDocument();
  });

  it("shows a message when there are no questions", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<QuestionPanelPage />);

    await screen.findByText("Quiz Questions Panel");
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/questions/"));

    expect(await screen.findByText("No questions have been created yet.")).toBeInTheDocument();
  });

  it("shows an error message when loading questions fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<QuestionPanelPage />);

    expect(await screen.findByText("Failed to load questions.")).toBeInTheDocument();
  });

  it("disables the save button until a correct answer is selected", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");

    expect(screen.getByRole("button", { name: "Save question" })).toBeDisabled();

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);

    expect(screen.getByRole("button", { name: "Save question" })).not.toBeDisabled();
  });

  it("submits a new question and resets the form", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = {
      id: "q2",
      stem: "New question stem",
      subtitle: "New subtitle",
      choices: [
        { id: "a", label: "Choice A" },
        { id: "b", label: "Choice B" },
        { id: "c", label: "Choice C" },
        { id: "d", label: "Choice D" },
      ],
      correct_choice_id: "b",
    };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");

    const textboxes = screen.getAllByRole("textbox");
    fireEvent.change(textboxes[0], { target: { value: "New question stem" } });
    fireEvent.change(textboxes[1], { target: { value: "New subtitle" } });
    fireEvent.change(textboxes[2], { target: { value: "Choice A" } });
    fireEvent.change(textboxes[3], { target: { value: "Choice B" } });
    fireEvent.change(textboxes[4], { target: { value: "Choice C" } });
    fireEvent.change(textboxes[5], { target: { value: "Choice D" } });

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[1]);

    const saveButton = screen.getByRole("button", { name: "Save question" });
    expect(saveButton).not.toBeDisabled();
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            stem: "New question stem",
            subtitle: "New subtitle",
            choices: [
              { id: "a", label: "Choice A" },
              { id: "b", label: "Choice B" },
              { id: "c", label: "Choice C" },
              { id: "d", label: "Choice D" },
            ],
            correct_choice_id: "b",
          }),
        }),
      ),
    );

    expect(await screen.findByText("Question saved!")).toBeInTheDocument();
    expect((textboxes[0] as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByRole("button", { name: "Save question" })).toBeDisabled();
    expect(await screen.findByText("New question stem")).toBeInTheDocument();
  });

  it("shows an error message when saving a new question fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");

    const textboxes = screen.getAllByRole("textbox");
    fireEvent.change(textboxes[0], { target: { value: "stem" } });
    fireEvent.change(textboxes[2], { target: { value: "a" } });
    fireEvent.change(textboxes[3], { target: { value: "b" } });
    fireEvent.change(textboxes[4], { target: { value: "c" } });
    fireEvent.change(textboxes[5], { target: { value: "d" } });

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[0]);

    fireEvent.click(screen.getByRole("button", { name: "Save question" }));

    expect(await screen.findByText("Failed to save question.")).toBeInTheDocument();
  });

  it("edits a question and saves the changes", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "PUT") return Promise.resolve({ ...question1, stem: "Updated stem", correct_choice_id: "c" });
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByText("Editing question")).toBeInTheDocument();

    const textboxes = screen.getAllByRole("textbox");
    fireEvent.change(textboxes[6], { target: { value: "Updated stem" } });

    const radios = screen.getAllByRole("radio");
    fireEvent.click(radios[6]);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/q1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    expect(await screen.findByText("Updated stem")).toBeInTheDocument();
    expect(screen.queryByText("Editing question")).not.toBeInTheDocument();
  });

  it("cancels editing a question", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([question1]);
    render(<QuestionPanelPage />);

    await screen.findByText("What is 2+2?");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByText("Editing question")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Editing question")).not.toBeInTheDocument();
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
  });

  it("shows an alert when saving an edited question fails", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "PUT") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to update question."));
    alertSpy.mockRestore();
  });

  it("deletes a question after confirmation", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "DELETE") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/q1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText("What is 2+2?")).not.toBeInTheDocument());

    confirmSpy.mockRestore();
  });

  it("does not delete a question when confirmation is cancelled", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([question1]);

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/questions/q1", expect.anything());
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an alert when deleting a question fails", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "DELETE") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to delete question."));

    confirmSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it("navigates to the dashboard when Back to Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<QuestionPanelPage />);

    fireEvent.click(await screen.findByText("Back to Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<QuestionPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
