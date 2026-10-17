import {
  createReport,
  getMyReports,
  getAllReports,
  getReport,
  addComment,
  updateStatus,
} from "../../lib/reports";

describe("reports lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    }) as jest.Mock;
  });

  it("createReport posts to /api/reports with the report payload", async () => {
    const payload = { category: "bug" as const, description: "Broken choice" };
    await createReport(payload);

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
      })
    );
  });

  it("getMyReports requests the base endpoint when no status is given", async () => {
    await getMyReports();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getMyReports appends the status query param when given", async () => {
    await getMyReports("open");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports?status=open",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getAllReports requests the base endpoint when no status is given", async () => {
    await getAllReports();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getAllReports appends the status query param when given", async () => {
    await getAllReports("closed");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports?status=closed",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("getReport requests the single report endpoint", async () => {
    await getReport("r1");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports/r1",
      expect.objectContaining({ credentials: "include" })
    );
  });

  it("addComment posts the comment body to the report's comments endpoint", async () => {
    await addComment("r1", "Thanks for the update");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports/r1/comments",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ body: "Thanks for the update" }),
      })
    );
  });

  it("updateStatus patches the report's status endpoint", async () => {
    await updateStatus("r1", "resolved");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/reports/r1/status",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ status: "resolved" }),
      })
    );
  });
});
