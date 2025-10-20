import React from "react";
import { useEffect, useState } from "react";
import ChatBox from "../components/ChatBox";
import Link from "next/link";

export default function Home() {


  return (
    <div className="min-h-screen p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Motivation Exploring Platform</h1>
        <Link className="text-blue-600 hover:underline" href="/playground">Components Playground</Link>
      </div>
      <ChatBox />
    </div>
  );
}
