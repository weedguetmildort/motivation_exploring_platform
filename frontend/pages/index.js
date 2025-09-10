import { useEffect, useState } from "react";

export default function Home() {
  const [message, setMessage] = useState("Loading...");

  useEffect(() => {
    // Fetch from FastAPI backend
    fetch("http://localhost:8000/api/message")
      .then((res) => res.json())
      .then((data) => setMessage(data.message))
      .catch((err) => setMessage("Error fetching backend"));
  }, []);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
      <h1 className="text-4xl font-bold mb-4">AI Motivation Exploring Web Platform</h1>
      <p className="text-xl text-gray-700">{message}</p>
    </div>
  );
}
