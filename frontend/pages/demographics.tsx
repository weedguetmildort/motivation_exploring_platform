import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import { getMe, logout, type User } from "../lib/auth";
import { saveMyDemographics } from "../lib/demographics";

export default function DemographicsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [gender, setGender] = useState("");
  const [otherGender, setOtherGender] = useState("");
  const [raceEthnicity, setRaceEthnicity] = useState<string[]>([]);
  const [year, setYear] = useState("");
  const [major, setMajor] = useState("");

  useEffect(() => {
    let cancel = false;

    (async () => {
      try {
        const res = await getMe();
        if (cancel) return;

        const u = res.user;
        if (u.demographics_completed) {
          router.replace("/dashboard"); // already done
          return;
        }
        setUser(u);
      } catch {
        if (!cancel) router.replace("/login");
      } finally {
        if (!cancel) setChecking(false);
      }
    })();

    return () => {
      cancel = true;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center">
        <div className="text-gray-500">Loading…</div>
      </div>
    );
  }

  if (!user) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!gender || !raceEthnicity || !year) {
      setError("Please fill out the required fields.");
      return;
    }

    setSaving(true);
    try {
      await saveMyDemographics({
        gender: gender,
        other_gender: otherGender || undefined,
        race_ethnicity: raceEthnicity,
        year: year,
        major: major || undefined,
      });
      router.replace("/dashboard");
    } catch (e) {
      console.error(e);
      setError("Failed to save demographics.");
    } finally {
      setSaving(false);
    }
  }

  async function onLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">
              Demographics
            </h1>
            <p className="text-sm text-gray-600">
              Before you continue, please answer a few quick questions.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push("/profile")}
              className="text-sm px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
            >
              Profile
            </button>
            <button
              onClick={onLogout}
              className="bg-gray-100 hover:bg-gray-200 px-4 py-2 rounded-lg text-sm"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-xl mx-auto p-6">
        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-xl bg-white p-6 shadow-sm border"
        >
          {error && (
            <div className="text-sm text-red-600" role="alert">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Gender<span className="text-red-500">*</span>
            </label>
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
            >
              <option value="">Select gender</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Other">Self-describe</option>
              <option value="Prefer not to disclose">
                Prefer not to disclose
              </option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Self-describe gender
            </label>
            <input
              type="text"
              value={major}
              onChange={(e) => setOtherGender(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
              placeholder="e.g., Non-binary"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              How would you identify yourself in terms of race/ethnicity?
              <span className="text-red-500">*</span>
              <br />Please select all that apply to you.
            </label>

            <div className="space-y-2">
              {[
                { value: "white", label: "White" },
                { value: "hispanic", label: "Hispanic" },
                { value: "asian", label: "Asian" },
                { value: "middle_eastern", label: "Middle Eastern" },
                { value: "north_african", label: "North African" },
                { value: "black", label: "Black" },
                { value: "pacific_islander", label: "Pacific Islander" },
                { value: "indigenous", label: "Indigenous" },
                { value: "not_disclosed", label: "Prefer not to disclose" },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className="flex items-center gap-2 text-sm"
                >
                  <input
                    type="checkbox"
                    value={opt.value}
                    checked={raceEthnicity.includes(opt.value)}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      if (checked) {
                        setRaceEthnicity([...raceEthnicity, opt.value]);
                      } else {
                        setRaceEthnicity(
                          raceEthnicity.filter((v) => v !== opt.value)
                        );
                      }
                    }}
                    className="h-4 w-4 rounded border-gray-400"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              What is your year in college?
              <span className="text-red-500">*</span>
            </label>
            <select
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
            >
              <option value="">Select year in college</option>
              <option value="first">First Year</option>
              <option value="second">Second Year</option>
              <option value="third">Third Year</option>
              <option value="fourth">Fourth Year</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Major/Field of study
            </label>
            <input
              type="text"
              value={major}
              onChange={(e) => setMajor(e.target.value)}
              className="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring"
              placeholder="e.g., Computer Science"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg px-4 py-2 bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
            >
              {saving ? "Saving…" : "Continue"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
