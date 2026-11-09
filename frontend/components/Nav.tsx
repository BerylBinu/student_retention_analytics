"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./ui";

const LINKS = [
  { href: "/", text: "Overview", icon: "grid" },
  { href: "/students", text: "Students", icon: "users" },
  { href: "/demo", text: "Live demo", icon: "bolt" },
] as const;

export default function Nav() {
  const path = usePathname();
  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <nav className="flex gap-1 lg:flex-col">
      {LINKS.map((l) => (
        <Link
          key={l.href}
          href={l.href}
          className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
            isActive(l.href) ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-white"
          }`}
        >
          <Icon name={l.icon} className="h-4 w-4" />
          {l.text}
        </Link>
      ))}
    </nav>
  );
}