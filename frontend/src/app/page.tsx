"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Health = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

type State =
  | { kind: "loading" }
  | { kind: "ok"; health: Health }
  | { kind: "error"; message: string };

export default function Home() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_URL}/healthcheck`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<Health>;
      })
      .then((health) => {
        if (!cancelled) setState({ kind: "ok", health });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Unknown error",
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-3">
        <h1 className="text-4xl font-semibold tracking-tight">
          The Right Basket
        </h1>
        <p className="text-base text-neutral-600 dark:text-neutral-400">
          Project scaffolding is in place. Next.js and Tailwind CSS on the
          frontend, FastAPI on the backend.
        </p>
      </div>

      <section className="rounded-lg border border-neutral-200 p-5 dark:border-neutral-800">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-500">
          Backend status
        </h2>

        {state.kind === "loading" && (
          <p className="text-sm text-neutral-500">
            Checking <code>{API_URL}/healthcheck</code>…
          </p>
        )}

        {state.kind === "ok" && (
          <div className="flex flex-col gap-1 text-sm">
            <p className="font-medium text-emerald-600 dark:text-emerald-400">
              Connected — {state.health.status}
            </p>
            <p className="text-neutral-600 dark:text-neutral-400">
              {state.health.service} v{state.health.version} (
              {state.health.environment})
            </p>
          </div>
        )}

        {state.kind === "error" && (
          <div className="flex flex-col gap-1 text-sm">
            <p className="font-medium text-amber-600 dark:text-amber-400">
              Not reachable — {state.message}
            </p>
            <p className="text-neutral-600 dark:text-neutral-400">
              Start the API from the <code>backend/</code> directory, then
              reload.
            </p>
          </div>
        )}
      </section>
    </main>
  );
}
