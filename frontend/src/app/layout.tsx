import type { Metadata } from "next";
import { Suspense } from "react";
import { I18nProvider } from "@/i18n/context";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Marketing Intelligence Platform",
  description: "Competitive intelligence and content automation for marketers",
  manifest: "/manifest.json",
  themeColor: "#4f46e5",
};

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-gray-500">Loading...</p>
    </div>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <I18nProvider>
          <Suspense fallback={<LoadingFallback />}>
            {children}
          </Suspense>
        </I18nProvider>
      </body>
    </html>
  );
}
