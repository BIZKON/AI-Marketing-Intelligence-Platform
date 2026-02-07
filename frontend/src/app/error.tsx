"use client";

import { useEffect } from "react";
import { useI18n } from "@/i18n/context";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useI18n();

  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
          {t("error", "title")}
        </h2>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
          {error.message || t("error", "defaultMessage")}
        </p>
        <button
          onClick={reset}
          className="mt-4 rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500 transition-colors"
        >
          {t("error", "tryAgain")}
        </button>
      </div>
    </div>
  );
}
