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
            set: null,
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

  const qStatsEasy = {
    id: "qs1", stem: "Statistics", subtitle: "s1",
    choices: [{ id: "a", label: "1" }, { id: "b", label: "2" }], correct_choice_id: "a",
    set: "a", difficulty: "easy", difficulty_source: "ai", difficulty_checked: true,
  };
  const qStatsHard = {
    id: "qs2", stem: "Statistics", subtitle: "s2",
    choices: [{ id: "a", label: "1" }, { id: "b", label: "2" }], correct_choice_id: "b",
    set: "b", difficulty: "hard", difficulty_source: "manual", difficulty_checked: true,
  };
  const qPermUnjudged = {
    id: "qp1", stem: "Permutations", subtitle: "s3",
    choices: [{ id: "a", label: "1" }, { id: "b", label: "2" }], correct_choice_id: "a",
    set: null, difficulty: null, difficulty_source: null, difficulty_checked: false,
  };

  it("renders topic, difficulty, and set count rows", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([qStatsEasy, qStatsHard, qPermUnjudged]);
    render(<QuestionPanelPage />);

    // Topic counts (grouped by stem)
    expect(await screen.findByText("Statistics 2")).toBeInTheDocument();
    expect(screen.getByText("Permutations 1")).toBeInTheDocument();
    // Difficulty counts
    expect(screen.getByText("Easy 1")).toBeInTheDocument();
    expect(screen.getByText("Medium 0")).toBeInTheDocument();
    expect(screen.getByText("Hard 1")).toBeInTheDocument();
    expect(screen.getByText("Unjudged 1")).toBeInTheDocument();
    // Set counts
    expect(screen.getByText("A 1")).toBeInTheDocument();
    expect(screen.getByText("B 1")).toBeInTheDocument();
    expect(screen.getByText("C 0")).toBeInTheDocument();
    expect(screen.getByText("D 0")).toBeInTheDocument();
    expect(screen.getByText("Unassigned 1")).toBeInTheDocument();
  });

  it("shows difficulty and set badges with source labels on each card", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([qStatsEasy, qStatsHard, qPermUnjudged]);
    render(<QuestionPanelPage />);

    await screen.findByText("Statistics 2");
    expect(screen.getByText("Easy · AI")).toBeInTheDocument();
    expect(screen.getByText("Hard · manual")).toBeInTheDocument();
    expect(screen.getByText("Set A")).toBeInTheDocument();
    expect(screen.getByText("Set B")).toBeInTheDocument();
    expect(screen.getByText("Set —")).toBeInTheDocument();
  });

  it("assigns a set via the inline dropdown", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "PATCH") return Promise.resolve({ ...question1, set: "c" });
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.change(screen.getByLabelText("Set for What is 2+2?"), { target: { value: "c" } });

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/q1/set",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ set: "c" }) }),
      ),
    );
    expect(await screen.findByText("Set C")).toBeInTheDocument();
  });

  it("overrides difficulty via the inline dropdown", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "PATCH")
        return Promise.resolve({ ...question1, difficulty: "hard", difficulty_source: "manual", difficulty_checked: true });
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.change(screen.getByLabelText("Difficulty for What is 2+2?"), { target: { value: "hard" } });

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/q1/difficulty",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ difficulty: "hard" }) }),
      ),
    );
    expect(await screen.findByText("Hard · manual")).toBeInTheDocument();
  });

  it("shows an alert when assigning a set fails", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([question1]);
      if (method === "PATCH") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("What is 2+2?");

    fireEvent.change(screen.getByLabelText("Set for What is 2+2?"), { target: { value: "a" } });

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to assign set."));
    alertSpy.mockRestore();
  });

  it("runs difficulty judging and reloads the list", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    let getCount = 0;
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (url === "/api/questions/judge-difficulty") return Promise.resolve({ judged: 2, skipped: 0 });
      if (method === "GET") {
        getCount += 1;
        return Promise.resolve(
          getCount === 1
            ? [qPermUnjudged]
            : [{ ...qPermUnjudged, difficulty: "medium", difficulty_source: "ai", difficulty_checked: true }],
        );
      }
      return Promise.resolve(undefined);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("Permutations");

    fireEvent.click(screen.getByRole("button", { name: "Judge difficulty now" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/questions/judge-difficulty",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText(/Judged 2 questions\./)).toBeInTheDocument();
    expect(await screen.findByText("Medium · AI")).toBeInTheDocument();
  });

  it("saves a new question straight into the chosen set and keeps the set for the next one", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      if ((init?.method ?? "GET") === "GET") return Promise.resolve([]);
      return Promise.resolve({ ...question1, id: "q9", stem: "Sets question", set: "c" });
    });

    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");
    const textboxes = screen.getAllByRole("textbox");
    fireEvent.change(textboxes[0], { target: { value: "Sets question" } });
    ["1", "2", "3", "4"].forEach((label, index) => fireEvent.change(textboxes[index + 2], { target: { value: label } }));
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.change(screen.getByLabelText("Set"), { target: { value: "c" } });
    fireEvent.click(screen.getByRole("button", { name: "Save question" }));

    await waitFor(() => {
      const post = mockApiFetch.mock.calls.find(([, init]) => init?.method === "POST");
      expect(post).toBeDefined();
      expect(JSON.parse(post![1].body)).toEqual(expect.objectContaining({ set: "c", correct_choice_id: "a" }));
    });
    expect(await screen.findByText("Question saved!")).toBeInTheDocument();
    expect(screen.getByLabelText("Set")).toHaveValue("c");
    expect(screen.getByLabelText("Set for Sets question")).toHaveValue("c");
  });

  it("offers Unassigned and every set when adding a question", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");
    const select = screen.getByLabelText("Set");
    expect(select).toHaveValue("");
    expect(Array.from((select as HTMLSelectElement).options).map(option => option.textContent)).toEqual(["Unassigned", "A", "B", "C", "D"]);
  });

  it("reloads the whole list after a CSV import", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    let gets = 0;
    const report = { dry_run: true, valid: true, rows: 1, to_import: 1, imported: 0,
      by_set: { a: 0, b: 0, c: 1, d: 0, unassigned: 0 }, errors: [], skipped: [] };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      if (url === "/api/questions/import") {
        const dryRun = JSON.parse(init.body).dry_run;
        return Promise.resolve({ ...report, dry_run: dryRun, imported: dryRun ? 0 : 1 });
      }
      gets += 1;
      return Promise.resolve(gets === 1 ? [] : [{ ...question1, id: "q7", stem: "Imported topic", set: "c" }]);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("No questions have been created yet.");
    const file = new File(["topic,question,a,b,c,d,correct,set\nImported topic,Q,1,2,3,4,a,c\n"], "bank.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("Question CSV"), { target: { files: [file] } });
    fireEvent.click(await screen.findByRole("button", { name: "Import 1 question" }));

    expect(await screen.findByText("Imported topic")).toBeInTheDocument();
    expect(gets).toBe(2);
  });

  it("shows an error when difficulty judging fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      if (url === "/api/questions/judge-difficulty") return Promise.reject(new Error("server error"));
      return Promise.resolve([qPermUnjudged]);
    });

    render(<QuestionPanelPage />);
    await screen.findByText("Permutations");

    fireEvent.click(screen.getByRole("button", { name: "Judge difficulty now" }));

    expect(await screen.findByText("Failed to run difficulty judging.")).toBeInTheDocument();
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
