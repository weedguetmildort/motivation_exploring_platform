import React from "react";
import { useEffect, useState } from "react";
import ChatBox from "../components/ChatBox";

export default function Home() {


  return (
    <div className="min-h-screen p-6">
      <h1 className="text-2xl font-bold mb-4">Motivation Exploring Platform</h1>
      <ChatBox />
    </div>
  );
}
