import type { Metadata } from "next";
import { DM_Sans, DM_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const dmMono = DM_Mono({
  variable: "--font-dm-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Cooko — Supermarktprijzen vergelijken",
  description:
    "Vergelijk producten bij AH, Jumbo, PLUS, Dirk en meer. Vind altijd de goedkoopste aanbieding.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="nl"
      className={`${dmSans.variable} ${dmMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        {/* Header */}
        <header
          className="sticky top-0 z-10 border-b"
          style={{
            backgroundColor: "rgba(255,255,255,0.9)",
            backdropFilter: "blur(8px)",
            borderColor: "#f3f4f6",
          }}
        >
          <div className="mx-auto flex h-14 max-w-2xl items-center justify-between px-4">
            <Link
              href="/"
              className="flex items-center gap-1.5 font-bold text-lg tracking-tight transition-opacity hover:opacity-80"
              style={{
                fontFamily: "var(--font-dm-sans)",
                color: "#111827",
                letterSpacing: "-0.02em",
              }}
            >
              cooko
              <span aria-hidden="true">🌿</span>
            </Link>
            <span className="text-xs" style={{ color: "#d1d5db" }}>
              beta
            </span>
          </div>
        </header>

        {/* Main content */}
        <main className="flex flex-1 flex-col">{children}</main>

        {/* Footer */}
        <footer
          className="border-t py-6 text-center text-xs"
          style={{ borderColor: "#f3f4f6", color: "#d1d5db" }}
        >
          Prijzen worden regelmatig bijgewerkt · Cooko {new Date().getFullYear()}
        </footer>
      </body>
    </html>
  );
}
