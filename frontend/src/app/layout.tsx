import type { Metadata, Viewport } from "next";
import { Suspense } from "react";
import "./globals.css";
import { ServiceWorkerRegistrar } from "./sw-registrar";

export const metadata: Metadata = {
  title: "AI Marketing Intelligence Platform",
  description: "Competitive intelligence and content automation for marketers",
  manifest: "/manifest.json",
};

export const viewport: Viewport = {
  themeColor: "#4f46e5",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
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
    <html lang="en">
      <body className="min-h-screen bg-gray-50 dark:bg-gray-950">
        <ServiceWorkerRegistrar />
        <Suspense fallback={<LoadingFallback />}>
          {children}
        </Suspense>
      </body>
    </html>
  );
}
