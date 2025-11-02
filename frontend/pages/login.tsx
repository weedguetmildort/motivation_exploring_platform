import AuthForm from "../components/AuthForm";

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <AuthForm mode="login" />
    </div>
  );
}