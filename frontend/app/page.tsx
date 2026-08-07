"use client";

import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type HealthState =
  | { status: "loading" }
  | { status: "ok"; body: unknown }
  | { status: "error"; message: string };

export default function HomePage() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE_URL}/health`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Backend responded with ${response.status}`);
        }
        return response.json();
      })
      .then((body) => {
        if (!cancelled) setHealth({ status: "ok", body });
      })
      .catch((error: Error) => {
        if (!cancelled) setHealth({ status: "error", message: error.message });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-3xl font-semibold">CareerOS</h1>
      <p className="text-slate-400">Personal Career Operating System -- Phase 1 scaffold</p>
      <div className="rounded-lg border border-slate-800 bg-slate-900 px-6 py-4 text-sm">
        {health.status === "loading" && <span>Checking backend at {API_BASE_URL}...</span>}
        {health.status === "ok" && (
          <span className="text-emerald-400">Backend healthy: {JSON.stringify(health.body)}</span>
        )}
        {health.status === "error" && (
          <span className="text-rose-400">
            Could not reach backend at {API_BASE_URL}: {health.message}
          </span>
        )}
      </div>
    </main>
  );
}
