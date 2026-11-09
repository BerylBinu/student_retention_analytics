import type { Metadata } from "next";
import Link from "next/link";
import Nav from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Student Retention Analytics",
  description: "Early warning dashboard for at-risk students",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-100 text-slate-900 antialiased">
        <div className="lg:flex">
          {/* Sidebar (top bar on small screens) */}
          <aside className="bg-slate-900 lg:fixed lg:inset-y-0 lg:w-60">
            <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4 lg:h-full lg:flex-col lg:items-stretch lg:justify-start lg:px-4 lg:py-6">
              <Link href="/" className="flex items-center gap-3 lg:mb-8 lg:px-2">
                <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 text-sm font-bold text-white shadow-lg shadow-indigo-900/40">
                  SR
                </span>
                <span className="leading-tight">
                  <span className="block text-sm font-semibold text-white">Retention AI</span>
                  <span className="block text-xs text-slate-400">Early warning system</span>
                </span>
              </Link>
              <Nav />
              <div className="mt-auto hidden rounded-xl bg-white/5 p-3 text-xs text-slate-400 lg:block">
                <p className="flex items-center gap-2 font-medium text-slate-200">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
                  </span>
                  Pipeline live
                </p>
                <p className="mt-1.5 leading-relaxed">AWS S3, Lambda, DynamoDB and Gemini AI in Sydney (ap-southeast-2)</p>
              </div>
            </div>
          </aside>

          <main className="min-w-0 flex-1 lg:pl-60">
            <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}