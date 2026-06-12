import { saveMyDemographics, DemographicsPayload } from "../../lib/demographics";

describe("saveMyDemographics", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => JSON.stringify({ ok: true }),
    });
  });

  it("posts the payload to /api/demographics/me", async () => {
    const payload: DemographicsPayload = {
      gender: "female",
      race_ethnicity: ["asian"],
      year: "junior",
      age: "21",
    };

    const result = await saveMyDemographics(payload);

    expect(result).toEqual({ ok: true });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/demographics/me",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
        credentials: "include",
      })
    );
  });
});
