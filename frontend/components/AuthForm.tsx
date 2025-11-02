import { useState } from "react";
import { useRouter } from "next/router";
import { login, signup } from "../lib/auth";

type Props = {
  mode: "login" | "signup";
};

export default function AuthForm({ mode }: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending) return;

    setError(null);
    setPending(true);
    try {
      if (mode === "login") {
        await login(email.trim(), password);
      } else {
        await signup(email.trim(), password);
      }
      // On success, go to chat
      router.push("/dashboard");
    } catch (err: any) {
      setError(err?.message || "Something went wrong.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form
      onSubmit={onSubmit}
      className="mx-auto mt-16 max-w-sm rounded-2xl border bg-white p-6 shadow-sm"
    >
      <h1 className="mb-4 text-xl font-semibold">
        {mode === "login" ? "Log in" : "Create an account"}
      </h1>

      <label className="mb-2 block text-sm font-medium">Email</label>
      <input
        type="email"
        autoComplete="email"
        className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
        placeholder="you@example.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />

      <label className="mb-2 block text-sm font-medium">Password</label>
      <input
        type="password"
        autoComplete={mode === "login" ? "current-password" : "new-password"}
        className="mb-4 w-full rounded-xl border px-3 py-2 focus:outline-none focus:ring"
        placeholder="••••••••"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />

      {error && (
        <div role="alert" className="mb-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={pending}
        className="w-full rounded-xl bg-blue-600 px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
      </button>

      <p className="mt-4 text-center text-sm text-gray-600">
        {mode === "login" ? (
          <>
            Don&apos;t have an account?{" "}
            <a className="text-blue-600 underline" href="/signup">
              Sign up
            </a>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <a className="text-blue-600 underline" href="/login">
              Log in
            </a>
          </>
        )}
      </p>
    </form>
  );
}