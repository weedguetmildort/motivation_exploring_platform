import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SurveyPanelPage from "../../pages/surveys_panel";
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

const likertItem = {
  id: "item1",
  stage: "pre_quiz",
  prompt: "I feel motivated to learn.",
  type: "likert" as const,
  required: true,
  order: 0,
  active: true,
  category: "Motivation",
  reverse_scored: false,
  scale: { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] },
};

const singleSelectItem = {
  id: "item2",
  stage: "post_base",
  prompt: "Which best describes your experience?",
  type: "single_select" as const,
  required: false,
  order: 1,
  active: true,
  category: null,
  reverse_scored: false,
  options: [
    { id: "a", label: "Easy" },
    { id: "b", label: "Hard" },
  ],
};

describe("SurveyPanelPage", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockPush.mockClear();
    mockGetMe.mockReset();
    mockLogout.mockReset();
    mockApiFetch.mockReset();
  });

  it("shows a loading state before the session check resolves", () => {
    mockGetMe.mockReturnValue(new Promise(() => {}));
    render(<SurveyPanelPage />);
    expect(screen.getByText("Loading survey questions panel…")).toBeInTheDocument();
  });

  it("redirects non-admin users to the dashboard", async () => {
    mockGetMe.mockResolvedValue({ user: { id: "2", email: "user@example.com", is_admin: false } });
    render(<SurveyPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Survey Questions Panel")).not.toBeInTheDocument();
  });

  it("redirects to login when the session check fails", async () => {
    mockGetMe.mockRejectedValue(new Error("not authenticated"));
    render(<SurveyPanelPage />);

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });

  it("renders the panel and loads survey items for an admin user", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([likertItem, singleSelectItem]);
    render(<SurveyPanelPage />);

    expect(await screen.findByText("Survey Questions Panel")).toBeInTheDocument();
    expect(await screen.findByText("I feel motivated to learn.")).toBeInTheDocument();
    expect(screen.getByText(/Scale: 1–5/)).toBeInTheDocument();
    expect(screen.getByText(/Strongly disagree ↔ Strongly agree/)).toBeInTheDocument();
    expect(screen.getByText(/required/)).toBeInTheDocument();

    expect(screen.getByText("Which best describes your experience?")).toBeInTheDocument();
    expect(screen.getByText("Easy")).toBeInTheDocument();
    expect(screen.getByText("Hard")).toBeInTheDocument();
  });

  it("shows a message when there are no survey items", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);

    await screen.findByText("Survey Questions Panel");
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/surveys/items"));

    expect(await screen.findByText("No survey items yet.")).toBeInTheDocument();
  });

  it("shows an error message when loading survey items fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockRejectedValue(new Error("network error"));
    render(<SurveyPanelPage />);

    expect(await screen.findByText("Failed to load survey questions.")).toBeInTheDocument();
  });

  it("shows a validation message when the prompt is empty", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    const { container } = render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    const form = container.querySelector("form")!;
    fireEvent.submit(form);

    expect(await screen.findByText("Prompt is required.")).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items", expect.objectContaining({ method: "POST" }));
  });

  it("shows a validation message when the likert min is not less than max", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "I trust the system." } });

    const numberInputs = screen.getAllByRole("spinbutton");
    fireEvent.change(numberInputs[0], { target: { value: "5" } });
    fireEvent.change(numberInputs[1], { target: { value: "5" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    expect(await screen.findByText("Likert scale min must be less than max.")).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items", expect.objectContaining({ method: "POST" }));
  });

  it("shows a validation message when single-select has fewer than 2 options", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "Pick one." } });

    fireEvent.change(screen.getAllByRole("combobox")[1], { target: { value: "single_select" } });

    const optionInputs = screen.getAllByRole("textbox").filter((el) => el.tagName === "INPUT");
    fireEvent.change(optionInputs[optionInputs.length - 5], { target: { value: "Only one option" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    expect(await screen.findByText("Single-select requires at least 2 options.")).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items", expect.objectContaining({ method: "POST" }));
  });

  it("creates a new likert survey item and resets the form", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = {
      ...likertItem,
      id: "item3",
      prompt: "New prompt",
      category: "TRUST",
    };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "New prompt" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            stage: "pre_quiz",
            category: "TRUST",
            prompt: "New prompt",
            type: "likert",
            required: true,
            reverse_scored: false,
            order: 0,
            active: true,
            scale: {
              min: 1,
              max: 5,
              anchors: ["Strongly disagree", "Strongly agree"],
            },
          }),
        }),
      ),
    );

    expect(await screen.findByText("Survey item added.")).toBeInTheDocument();
    expect((textareas[0] as HTMLTextAreaElement).value).toBe("");
    expect(await screen.findByText("New prompt")).toBeInTheDocument();
  });

  it("creates a new single-select survey item with sanitized options", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = {
      ...singleSelectItem,
      id: "item4",
      prompt: "Pick one",
      category: null,
    };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "Pick one" } });

    fireEvent.change(screen.getAllByRole("combobox")[1], { target: { value: "single_select" } });

    const optionInputs = screen.getAllByRole("textbox").filter((el) => el.tagName === "INPUT");
    fireEvent.change(optionInputs[optionInputs.length - 5], { target: { value: "Option A" } });
    fireEvent.change(optionInputs[optionInputs.length - 4], { target: { value: "Option B" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            stage: "pre_quiz",
            category: "TRUST",
            prompt: "Pick one",
            type: "single_select",
            required: true,
            reverse_scored: false,
            order: 0,
            active: true,
            options: [
              { id: "a", label: "Option A" },
              { id: "b", label: "Option B" },
            ],
          }),
        }),
      ),
    );

    expect(await screen.findByText("Survey item added.")).toBeInTheDocument();
  });

  it("shows an error message when creating a survey item fails", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "New prompt" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    expect(await screen.findByText("Failed to add survey item.")).toBeInTheDocument();
  });

  it("toggles required and reverse-scored checkboxes", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    const requiredCheckbox = document.getElementById("required") as HTMLInputElement;
    const reverseCheckbox = document.getElementById("reverse") as HTMLInputElement;

    expect(requiredCheckbox.checked).toBe(true);
    expect(reverseCheckbox.checked).toBe(false);

    fireEvent.click(requiredCheckbox);
    fireEvent.click(reverseCheckbox);

    expect(requiredCheckbox.checked).toBe(false);
    expect(reverseCheckbox.checked).toBe(true);
  });

  it("edits a likert survey item and saves the changes", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const updated = { ...likertItem, prompt: "Updated prompt" };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem]);
      if (method === "PUT") return Promise.resolve(updated);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    const editPrompt = textareas[textareas.length - 1];
    fireEvent.change(editPrompt, { target: { value: "Updated prompt" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items/item1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    expect(await screen.findByText("Updated prompt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("shows an alert when the edited likert min is not less than max", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([likertItem]);

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const numberInputs = screen.getAllByRole("spinbutton");
    const editMin = numberInputs[numberInputs.length - 2];
    const editMax = numberInputs[numberInputs.length - 1];
    fireEvent.change(editMin, { target: { value: "5" } });
    fireEvent.change(editMax, { target: { value: "5" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(alertSpy).toHaveBeenCalledWith("Likert scale min must be less than max.");
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items/item1", expect.objectContaining({ method: "PUT" }));

    alertSpy.mockRestore();
  });

  it("edits a single-select item and validates option count", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([singleSelectItem]);

    render(<SurveyPanelPage />);
    await screen.findByText("Which best describes your experience?");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const editTypeSelects = screen.getAllByRole("combobox").filter((el) => (el as HTMLSelectElement).value === "single_select");
    const editType = editTypeSelects[editTypeSelects.length - 1];

    const optionInputs = screen.getAllByRole("textbox").filter((el) => el.tagName === "INPUT");
    const editOptionB = optionInputs[optionInputs.length - 1];
    fireEvent.change(editOptionB, { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(alertSpy).toHaveBeenCalledWith("Single-select requires at least 2 options.");
    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items/item2", expect.objectContaining({ method: "PUT" }));

    alertSpy.mockRestore();
  });

  it("cancels editing a survey item without saving", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([likertItem]);

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.getByText("I feel motivated to learn.")).toBeInTheDocument();
  });

  it("shows an alert when saving an edited survey item fails", async () => {
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem]);
      if (method === "PUT") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to update survey item."));
    alertSpy.mockRestore();
  });

  it("deletes a survey item after confirmation", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem]);
      if (method === "DELETE") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items/item1",
        expect.objectContaining({ method: "DELETE" }),
      ),
    );
    await waitFor(() => expect(screen.queryByText("I feel motivated to learn.")).not.toBeInTheDocument());

    confirmSpy.mockRestore();
  });

  it("does not delete a survey item when confirmation is cancelled", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(false);
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([likertItem]);

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/surveys/items/item1", expect.anything());
    expect(screen.getByText("I feel motivated to learn.")).toBeInTheDocument();

    confirmSpy.mockRestore();
  });

  it("shows an alert when deleting a survey item fails", async () => {
    const confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
    const alertSpy = jest.spyOn(window, "alert").mockImplementation(() => {});
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem]);
      if (method === "DELETE") return Promise.reject(new Error("server error"));
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to delete survey item."));

    confirmSpy.mockRestore();
    alertSpy.mockRestore();
  });

  it("changes stage, scale labels, and bounds when creating a likert item", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = { ...likertItem, id: "itemX", stage: "post_base", prompt: "P" };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    // Stage select (create form, first combobox)
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "post_base" } });
    fireEvent.change(screen.getByPlaceholderText("e.g., TRUST, NFC, AI Literacy"), { target: { value: "TRUST" } });
    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "P" } });

    // Scale left/right labels (only the create-form inputs carry these values while no items exist)
    fireEvent.change(screen.getByDisplayValue("Strongly disagree"), { target: { value: "Low" } });
    fireEvent.change(screen.getByDisplayValue("Strongly agree"), { target: { value: "High" } });

    const spin = screen.getAllByRole("spinbutton");
    fireEvent.change(spin[0], { target: { value: "0" } });
    fireEvent.change(spin[1], { target: { value: "6" } });

    fireEvent.click(screen.getByRole("button", { name: "Save survey item" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            stage: "post_base",
            category: "TRUST",
            prompt: "P",
            type: "likert",
            required: true,
            reverse_scored: false,
            order: 0,
            active: true,
            scale: { min: 0, max: 6, anchors: ["Low", "High"] },
          }),
        }),
      ),
    );
  });

  it("edits every field of a likert item and saves the changes", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const updated = { ...likertItem, prompt: "I feel motivated to learn." };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem]);
      if (method === "PUT") return Promise.resolve(updated);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    // Stage (edit form renders it as a text input valued "pre_quiz")
    fireEvent.change(screen.getByDisplayValue("pre_quiz"), { target: { value: "post_base" } });
    // Category (edit input valued "Motivation")
    fireEvent.change(screen.getByDisplayValue("Motivation"), { target: { value: "TRUST" } });

    // Min/Max (edit spinbuttons are the last two)
    const spin = screen.getAllByRole("spinbutton");
    fireEvent.change(spin[spin.length - 2], { target: { value: "2" } });
    fireEvent.change(spin[spin.length - 1], { target: { value: "7" } });

    // Anchors (edit inputs are the last occurrence of each default value)
    const lefts = screen.getAllByDisplayValue("Strongly disagree");
    fireEvent.change(lefts[lefts.length - 1], { target: { value: "Nope" } });
    const rights = screen.getAllByDisplayValue("Strongly agree");
    fireEvent.change(rights[rights.length - 1], { target: { value: "Yep" } });

    // Flags (edit checkboxes are the last three)
    const checks = screen.getAllByRole("checkbox");
    fireEvent.click(checks[checks.length - 3]); // required: true -> false
    fireEvent.click(checks[checks.length - 2]); // reverse_scored: false -> true
    fireEvent.click(checks[checks.length - 1]); // active: true -> false

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items/item1",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const putCall = mockApiFetch.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1].body);
    expect(body).toMatchObject({
      stage: "post_base",
      category: "TRUST",
      type: "likert",
      required: false,
      reverse_scored: true,
      active: false,
      scale: { min: 2, max: 7, anchors: ["Nope", "Yep"] },
      options: null,
    });
  });

  it("edits a single-select item's options and saves successfully", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const updated = { ...singleSelectItem, options: [{ id: "a", label: "AA" }, { id: "b", label: "Hard" }] };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([singleSelectItem]);
      if (method === "PUT") return Promise.resolve(updated);
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("Which best describes your experience?");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    fireEvent.change(screen.getByDisplayValue("Easy"), { target: { value: "AA" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items/item2",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    const putCall = mockApiFetch.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1].body);
    expect(body).toMatchObject({
      type: "single_select",
      options: [{ id: "a", label: "AA" }, { id: "b", label: "Hard" }],
      scale: null,
    });
  });

  it("switches an item's type within the edit form", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([likertItem]);

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    const combos = screen.getAllByRole("combobox");
    const editType = combos[combos.length - 1];

    fireEvent.change(editType, { target: { value: "single_select" } });
    expect(screen.getByText("Options (at least 2)")).toBeInTheDocument();

    fireEvent.change(editType, { target: { value: "likert" } });
    expect(screen.getAllByRole("spinbutton").length).toBeGreaterThan(0);
  });

  it("creates an item with a blank category and empty scale labels via fallbacks", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    const created = { ...likertItem, id: "itemY" };
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([]);
      if (method === "POST") return Promise.resolve(created);
      return Promise.resolve(undefined);
    });
    const { container } = render(<SurveyPanelPage />);
    await screen.findByText("No survey items yet.");

    const textareas = screen.getAllByRole("textbox").filter((el) => el.tagName === "TEXTAREA");
    fireEvent.change(textareas[0], { target: { value: "P" } });
    // Empty both scale labels so the anchor `|| fallback` branches are taken.
    fireEvent.change(screen.getByDisplayValue("Strongly disagree"), { target: { value: "" } });
    fireEvent.change(screen.getByDisplayValue("Strongly agree"), { target: { value: "" } });
    // Submit via the form element to bypass the HTML `required` category field (left blank → null).
    fireEvent.submit(container.querySelector("form")!);

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/surveys/items",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            stage: "pre_quiz",
            category: null,
            prompt: "P",
            type: "likert",
            required: true,
            reverse_scored: false,
            order: 0,
            active: true,
            scale: { min: 1, max: 5, anchors: ["Strongly disagree", "Strongly agree"] },
          }),
        }),
      ),
    );
  });

  it("renders a likert item with missing scale as optional and reverse-scored via display fallbacks", async () => {
    const sparse = {
      id: "sparse1",
      stage: "pre_quiz",
      prompt: "Sparse likert prompt",
      type: "likert" as const,
      required: false,
      order: 0,
      active: true,
      category: null,
      reverse_scored: true,
      // no scale field → display uses ?? fallbacks
    };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([sparse]);
    render(<SurveyPanelPage />);

    await screen.findByText("Sparse likert prompt");
    // The full display line uniquely identifies the fallbacks: 1–5 scale, default
    // anchors, reverse-scored (R), and optional (required=false).
    expect(
      screen.getByText(/Scale: 1–5 • Strongly disagree ↔ Strongly agree • \(R\) • optional/),
    ).toBeInTheDocument();
  });

  it("renders a single-select item with no options array", async () => {
    const sparse = {
      id: "sparse2",
      stage: "post_base",
      prompt: "Sparse select prompt",
      type: "single_select" as const,
      required: true,
      order: 0,
      active: true,
      category: null,
      reverse_scored: false,
      // no options field → list uses ?? [] fallback
    };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([sparse]);
    render(<SurveyPanelPage />);

    expect(await screen.findByText("Sparse select prompt")).toBeInTheDocument();
  });

  it("renders likert items with missing scale/anchors using fallback defaults", async () => {
    const noAnchors = { ...likertItem, id: "na", category: null, reverse_scored: true, required: false, scale: { min: 2, max: 6 } };
    const noScale = { ...likertItem, id: "ns", prompt: "No scale item", scale: null };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([noAnchors, noScale]);
    render(<SurveyPanelPage />);

    await screen.findByText("No scale item");
    // noAnchors: explicit 2–6 bounds, default anchor labels, reverse (R) + optional
    expect(screen.getByText(/Scale: 2–6 • Strongly disagree ↔ Strongly agree • \(R\) • optional/)).toBeInTheDocument();
    // noScale: min/max fall back to 1–5
    expect(screen.getByText(/Scale: 1–5/)).toBeInTheDocument();
  });

  it("edits a likert item that has no anchors and saves with fallback anchors", async () => {
    const noAnchors = { ...likertItem, id: "na", category: null, scale: { min: 2, max: 6 } };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([noAnchors]);
      if (method === "PUT") return Promise.resolve({ ...noAnchors });
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("I feel motivated to learn.");
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/surveys/items/na", expect.objectContaining({ method: "PUT" })),
    );
    const putCall = mockApiFetch.mock.calls.find(([, init]) => init?.method === "PUT");
    const body = JSON.parse(putCall![1].body);
    expect(body.scale.anchors).toEqual(["Strongly disagree", "Strongly agree"]);
    expect(body.category).toBeNull();
  });

  it("renders a single-select item that has no options array", async () => {
    const noOptions = { ...singleSelectItem, id: "no", prompt: "No options item", options: null };
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([noOptions]);
    render(<SurveyPanelPage />);

    expect(await screen.findByText("No options item")).toBeInTheDocument();
  });

  it("updates only the edited item when multiple are present", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockImplementation((url: string, init?: any) => {
      const method = init?.method ?? "GET";
      if (method === "GET") return Promise.resolve([likertItem, singleSelectItem]);
      if (method === "PUT") return Promise.resolve({ ...singleSelectItem, prompt: "Edited single" });
      return Promise.resolve(undefined);
    });

    render(<SurveyPanelPage />);
    await screen.findByText("Which best describes your experience?");

    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith("/api/surveys/items/item2", expect.objectContaining({ method: "PUT" })),
    );
    expect(screen.getByText("I feel motivated to learn.")).toBeInTheDocument();
    expect(await screen.findByText("Edited single")).toBeInTheDocument();
  });

  it("navigates to the dashboard when Back to Dashboard is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);

    fireEvent.click(await screen.findByText("Back to Dashboard"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("logs out and redirects to login when Logout is clicked", async () => {
    mockGetMe.mockResolvedValue({ user: adminUser });
    mockLogout.mockResolvedValue(undefined);
    mockApiFetch.mockResolvedValue([]);
    render(<SurveyPanelPage />);

    fireEvent.click(await screen.findByText("Logout"));

    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
  });
});
