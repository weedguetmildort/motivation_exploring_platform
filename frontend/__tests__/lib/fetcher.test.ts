import { apiFetch } from "../../lib/fetcher";

describe("apiFetch", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  it("sends credentials and JSON content-type by default", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ hello: "world" }),
    });

    const result = await apiFetch("/api/thing");

    expect(result).toEqual({ hello: "world" });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/thing",
      expect.objectContaining({
        credentials: "include",
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
  });

  it("merges custom headers with defaults", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => "{}",
    });

    await apiFetch("/api/thing", { headers: { "X-Custom": "abc" } });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/thing",
      expect.objectContaining({
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          "X-Custom": "abc",
        }),
      })
    );
  });

  it("returns null when response body is empty", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 204,
      statusText: "No Content",
      text: async () => "",
    });

    const result = await apiFetch("/api/thing");
    expect(result).toBeNull();
  });

  it("returns null when response body is not valid JSON", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => "not json",
    });

    const result = await apiFetch("/api/thing");
    expect(result).toBeNull();
  });

  it("throws an error using the 'detail' field on non-ok responses", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      text: async () => JSON.stringify({ detail: "Invalid input" }),
    });

    await expect(apiFetch("/api/thing")).rejects.toThrow("Invalid input");
  });

  it("throws an error using the 'message' field on non-ok responses", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Server Error",
      text: async () => JSON.stringify({ message: "Boom" }),
    });

    await expect(apiFetch("/api/thing")).rejects.toThrow("Boom");
  });

  it("falls back to status text when no JSON error fields are present", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      text: async () => "",
    });

    await expect(apiFetch("/api/thing")).rejects.toThrow("503 Service Unavailable");
  });
});
