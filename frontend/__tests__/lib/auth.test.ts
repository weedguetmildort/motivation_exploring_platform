import {
  signup,
  login,
  logout,
  getMe,
  invalidateMeCache,
  changePassword,
  recordConsentAgreement,
  recordConsentDecline,
  recordConsentViewed,
  sendConsentAbandonedBeacon,
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

  it("recordConsentAgreement posts consent_text to /auth/consent", async () => {
    mockFetchOnce({ ok: true });

    await recordConsentAgreement("Research Consent Form ... I agree to participate");

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/consent",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ consent_text: "Research Consent Form ... I agree to participate" }),
      })
    );
  });

  it("recordConsentDecline posts consent_text to /auth/decline", async () => {
    mockFetchOnce({ ok: true });

    await recordConsentDecline("Research Consent Form ... I do not wish to participate");

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/decline",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ consent_text: "Research Consent Form ... I do not wish to participate" }),
      })
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

  it("recordConsentViewed posts to /auth/consent-viewed", async () => {
    mockFetchOnce({ ok: true });

    await recordConsentViewed();

    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/consent-viewed",
      expect.objectContaining({ method: "POST" })
    );
  });

  describe("sendConsentAbandonedBeacon", () => {
    const originalSendBeacon = (navigator as any).sendBeacon;

    afterEach(() => {
      (navigator as any).sendBeacon = originalSendBeacon;
    });

    it("uses navigator.sendBeacon (not fetch) when it is available", () => {
      const beacon = jest.fn();
      (navigator as any).sendBeacon = beacon;

      sendConsentAbandonedBeacon();

      expect(beacon).toHaveBeenCalledWith("/auth/consent-abandoned");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("falls back to a keepalive POST when sendBeacon is unavailable", () => {
      (navigator as any).sendBeacon = undefined;
      mockFetchOnce({ ok: true });

      sendConsentAbandonedBeacon();

      expect(global.fetch).toHaveBeenCalledWith(
        "/auth/consent-abandoned",
        expect.objectContaining({
          method: "POST",
          keepalive: true,
          credentials: "include",
        })
      );
    });
  });

  describe("getMe", () => {
    it("does not let an invalidated in-flight request overwrite fresh progress", async () => {
      let finishOld!: (response: any) => void;
      (global.fetch as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finishOld = resolve; }));
      const oldRequest = getMe();
      invalidateMeCache();
      const fresh = { user: { id: "new-user", completed_steps: ["survey:pre_quiz"] } };
      mockFetchOnce(fresh);
      await getMe();
      finishOld({ ok: true, text: async () => JSON.stringify({ user: { id: "old-user", completed_steps: [] } }) });
      await oldRequest;
      expect(await getMe()).toEqual(fresh);
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });

    it("does not let an old failed request clear a newer pending request", async () => {
      let failOld!: (error: Error) => void;
      let finishNew!: (response: any) => void;
      (global.fetch as jest.Mock).mockReturnValueOnce(new Promise((_resolve, reject) => { failOld = reject; }));
      const oldRequest = getMe().catch(() => {});
      invalidateMeCache();
      (global.fetch as jest.Mock).mockReturnValueOnce(new Promise(resolve => { finishNew = resolve; }));
      const newRequest = getMe();
      failOld(new Error("old session"));
      await oldRequest;
      const deduped = getMe();
      expect(global.fetch).toHaveBeenCalledTimes(2);
      finishNew({ ok: true, text: async () => JSON.stringify({ user: { id: "new" } }) });
      expect(await newRequest).toEqual(await deduped);
    });

    it("signup clears the previous account's cached session", async () => {
      mockFetchOnce({ user: { id: "previous" } });
      await getMe();
      mockFetchOnce({ user: { id: "new" } });
      await signup({ firstName: "Test", lastName: "User", email: "new@example.com", password: "password", consent: true });
      mockFetchOnce({ user: { id: "new" } });
      expect((await getMe()).user.id).toBe("new");
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

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
