import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "CareerOS",
  description: "Ranked, explained shortlist of jobs worth your time",
};

const NAV = [
  { href: "/", label: "Shortlist" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/insights", label: "Insights" },
  { href: "/gaps", label: "Gaps" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header
          className="sticky top-0 z-10 backdrop-blur"
          style={{ borderBottom: "1px solid var(--hairline)", background: "color-mix(in srgb, var(--plane) 88%, transparent)" }}
        >
          <div className="mx-auto flex max-w-6xl flex-wrap items-baseline gap-x-6 gap-y-2 px-5 py-3">
            <Link href="/" className="text-sm font-semibold tracking-tight">
              CareerOS
            </Link>
            <nav className="flex gap-4" aria-label="Sections">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-sm hover:underline"
                  style={{ color: "var(--ink-secondary)" }}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-5 py-6">{children}</main>
      </body>
    </html>
  );
}
