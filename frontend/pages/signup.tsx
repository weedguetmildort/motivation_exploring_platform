import AuthForm from "../components/AuthForm";

export default function SignupPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <AuthForm mode="signup" />
    </div>
  );
}