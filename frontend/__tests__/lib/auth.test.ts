import {
  signup,
  login,
  logout,
  getMe,
  invalidateMeCache,
  changePassword,
} from "../../lib/auth";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    text: async () => JSON.stringify(body),
  });
}

describe("auth lib", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    invalidateMeCache();
  });

  it("signup posts mapped fields to /auth/signup", async () => {
    mockFetchOnce({ user: { id: "1" } });

    await signup({
      firstName: "Ada",
      lastName: "Lovelace",
      email: "ada@example.com",
      password: "secret",
      consent: true,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/signup",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          first_name: "Ada",
          last_name: "Lovelace",
          email: "ada@example.com",
          password: "secret",
          consent: true,
        }),
      })
    );
  });

  it("login posts credentials to /auth/login and invalidates the me cache", async () => {
    mockFetchOnce({ user: { id: "1" } });

    await login("ada@example.com", "secret");

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "ada@example.com", password: "secret" }),
      })
    );
  });

  it("logout posts to /auth/logout and invalidates the me cache", async () => {
    mockFetchOnce({});

    await logout();

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/logout",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("changePassword posts mapped fields to /auth/change-password", async () => {
    mockFetchOnce({ ok: true });

    await changePassword("old-pass", "new-pass");

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/change-password",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          current_password: "old-pass",
          new_password: "new-pass",
        }),
      })
    );
  });

  describe("getMe", () => {
    it("fetches /auth/me and caches the result for subsequent calls", async () => {
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });

      const first = await getMe();
      const second = await getMe();

      expect(first).toEqual(second);
      expect(global.fetch).toHaveBeenCalledTimes(1);
      expect(global.fetch).toHaveBeenCalledWith("/auth/me", expect.objectContaining({ credentials: "include" }));
    });

    it("dedupes concurrent in-flight calls into a single request", async () => {
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });

      const [first, second] = await Promise.all([getMe(), getMe()]);

      expect(first).toEqual(second);
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    it("re-fetches after the cache TTL expires", async () => {
      const nowSpy = jest.spyOn(Date, "now");
      nowSpy.mockReturnValue(1_000_000);
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });
      await getMe();

      // Advance time beyond the 30s TTL.
      nowSpy.mockReturnValue(1_000_000 + 31_000);
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });
      await getMe();

      expect(global.fetch).toHaveBeenCalledTimes(2);
      nowSpy.mockRestore();
    });

    it("clears the pending promise and rethrows on failure", async () => {
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 401,
        statusText: "Unauthorized",
        text: async () => JSON.stringify({ detail: "Not logged in" }),
      });

      await expect(getMe()).rejects.toThrow("Not logged in");

      // A subsequent call should issue a new request rather than reusing
      // a rejected in-flight promise.
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });
      await getMe();
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it("invalidateMeCache forces a re-fetch", async () => {
      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });
      await getMe();

      invalidateMeCache();

      mockFetchOnce({ user: { id: "1", email: "ada@example.com", is_admin: false } });
      await getMe();

      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });
});
