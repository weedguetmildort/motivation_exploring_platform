import React from "react";
import { useEffect, useState } from "react";
import ChatBox from "../components/ChatBox";
import Link from "next/link";
import FollowUpQuestionBox from "../components/FollowUpQuestionBox";

export default function Landing() {
  return (
    <div className="grid min-h-screen place-items-center bg-gray-50 p-6">
      <div className="max-w-md rounded-2xl border bg-white p-6 shadow-sm">
        <h1 className="mb-2 text-xl font-semibold">
          Motivation Exploring Platform
        </h1>
        <p className="mb-4 text-sm text-gray-600">
          Sign up or log in to start chatting.
        </p>
        <div className="flex gap-3">
          <a
            href="/signup"
            className="rounded-xl bg-blue-600 px-4 py-2 text-white"
          >
            Sign up
          </a>
          <a
            href="/login"
            className="rounded-xl border px-4 py-2"
          >
            Log in
          </a>
        </div>
      </div>
    </div>
  );
}