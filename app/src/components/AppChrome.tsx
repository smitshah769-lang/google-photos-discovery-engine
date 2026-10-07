"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchJson, type ChromeMeta } from "@/lib/api";

const TABS = [
  { href: "/", label: "Discovery" },
  { href: "/search", label: "Search" },
  { href: "/how-it-works", label: "How it works" },
];

export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [apiError, setApiError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<ChromeMeta>("/chrome")
      .then(() => setApiError(null))
      .catch((err: Error) => setApiError(err.message));
  }, []);

  return (
    <div className="shell">
      <header className="chrome">
        <div className="chrome-top">
          <Image
            src="/google-photos-logo.png"
            alt="Google Photos"
            width={160}
            height={48}
            className="chrome-logo"
            priority
          />
          <h1 className="chrome-title">AI powered Discovery engine</h1>
        </div>
        <nav className="chrome-tabs" aria-label="Main">
          {TABS.map((tab) => (
            <Link key={tab.href} href={tab.href} className={pathname === tab.href ? "active" : ""}>
              {tab.label}
            </Link>
          ))}
        </nav>
      </header>
      {apiError ? (
        <div className="chrome-api-error" role="status">
          API offline: {apiError}. Start with <code>python -m pipeline serve &lt;run-id&gt;</code>
        </div>
      ) : null}
      {children}
    </div>
  );
}
