"use client";

import { useState } from "react";
import { getToken } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export default function ExportPage() {
  const { t } = useI18n();
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [loading, setLoading] = useState<string | null>(null);

  const handleExport = async (format: "csv" | "pdf" | "docx") => {
    const token = getToken();
    if (!token) return;
    setLoading(format);

    try {
      const params = new URLSearchParams();
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);

      const res = await fetch(
        `${API_BASE}/export/${format}?${params.toString()}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (!res.ok) throw new Error("Export failed");

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `training_report.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      alert(t("exportPage", "exportFailed"));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("exportPage", "title")}
          </h1>
          <LanguageSwitcher />
        </div>

        {/* Date filters */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4 dark:text-white">{t("exportPage", "dateRange")}</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                {t("exportPage", "startDate")}
              </label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                {t("exportPage", "endDate")}
              </label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
            </div>
          </div>
        </div>

        {/* Export buttons */}
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => handleExport("csv")}
            disabled={loading !== null}
            className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 hover:shadow-lg transition-shadow text-center disabled:opacity-50"
          >
            <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-lg flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="font-semibold dark:text-white">{t("exportPage", "csv")}</div>
            <div className="text-xs text-gray-500 mt-1">{t("exportPage", "csvDescription")}</div>
            {loading === "csv" && <div className="text-xs text-blue-500 mt-2">{t("exportPage", "downloading")}</div>}
          </button>

          <button
            onClick={() => handleExport("pdf")}
            disabled={loading !== null}
            className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 hover:shadow-lg transition-shadow text-center disabled:opacity-50"
          >
            <div className="w-12 h-12 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="font-semibold dark:text-white">{t("exportPage", "pdf")}</div>
            <div className="text-xs text-gray-500 mt-1">{t("exportPage", "pdfDescription")}</div>
            {loading === "pdf" && <div className="text-xs text-blue-500 mt-2">{t("exportPage", "downloading")}</div>}
          </button>

          <button
            onClick={() => handleExport("docx")}
            disabled={loading !== null}
            className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 hover:shadow-lg transition-shadow text-center disabled:opacity-50"
          >
            <div className="w-12 h-12 bg-blue-100 dark:bg-blue-900/30 rounded-lg flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="font-semibold dark:text-white">{t("exportPage", "docx")}</div>
            <div className="text-xs text-gray-500 mt-1">{t("exportPage", "docxDescription")}</div>
            {loading === "docx" && <div className="text-xs text-blue-500 mt-2">{t("exportPage", "downloading")}</div>}
          </button>
        </div>
      </div>
    </div>
  );
}
