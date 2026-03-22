import AuthForm from "../components/AuthForm";
import Disclaimer from "../components/Disclaimer";

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <AuthForm mode="login" />
      <div className="mx-auto mt-8 max-w-sm rounded-2xl border bg-white p-6 shadow-sm">
        <Disclaimer
          groupName="Emerging Technologies in Education Group"
          institution="University of Florida"
          contactEmail="weedguet.mildort@ufl.edu"
          supervisor="Dr. Neha Rani IRB Protocol #"
        />
      </div>
    </div>
  );
}
