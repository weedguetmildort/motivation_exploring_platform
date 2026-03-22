import React from "react";
import Disclaimer from "../components/Disclaimer";

export default function Landing() {
  return (
    <div className="grid min-h-screen place-items-center bg-gray-50 p-6">
      <div className="max-w-md rounded-2xl border bg-white p-6 shadow-sm">

        <h1 className="mb-2 text-xl font-semibold">
          Motivation Exploring Platform
        </h1>

        <p className="mb-4 text-sm text-gray-600">
          Sign up or log in to start.
        </p>

        <div className="mb-6 flex gap-3">
          <a
            href="/signup"
            className="rounded-xl bg-blue-600 px-4 py-2 text-white"
          >
            Sign up
          </a>
          <a href="/login" className="rounded-xl border px-4 py-2">
            Log in
          </a>
        </div>

        {/* Divider */}
        <div className="my-4 border-t" />

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
