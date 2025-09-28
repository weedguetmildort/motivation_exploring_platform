import React from "react";
import { useEffect, useState } from "react";
import ChatBox from "../components/ChatBox";

export default function Home() {

  const [msg, setMsg] = useState<string>("loading…");

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${url}/`)
      .then(r => r.json())
      .then(data => setMsg(data?.message ?? "no message"))
      .catch(() => setMsg("failed to fetch from backend"));
  }, []);

  return (
    <div>
      <h1>Motivation Exploring Platform</h1>
      <p>{msg}</p>
      <ChatBox />
    </div>
  );
}
