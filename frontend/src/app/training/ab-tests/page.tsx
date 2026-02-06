"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

interface ABTest {
  id: string;
  name: string;
  variant_a: string;
  variant_b: string;
  is_active: boolean;
  created_at: string;
}

interface ABTestDetail extends ABTest {
  results: {
    a: { count: number; avg_score: number | null };
    b: { count: number; avg_score: number | null };
  };
}

export default function ABTestsPage() {
  const [tests, setTests] = useState<ABTest[]>([]);
  const [selectedTest, setSelectedTest] = useState<ABTestDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  // Create form
  const [name, setName] = useState("");
  const [variantA, setVariantA] = useState("");
  const [variantB, setVariantB] = useState("");

  useEffect(() => {
    fetchTests();
  }, []);

  const fetchTests = async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/ab-tests/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTests(await res.json());
    } catch {} finally {
      setLoading(false);
    }
  };

  const fetchTestDetail = async (testId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/ab-tests/${testId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setSelectedTest(await res.json());
    } catch {}
  };

  const createTest = async () => {
    if (!name || !variantA || !variantB) return;
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/ab-tests/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name, variant_a: variantA, variant_b: variantB }),
      });
      if (res.ok) {
        setShowCreate(false);
        setName("");
        setVariantA("");
        setVariantB("");
        fetchTests();
      }
    } catch {}
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">A/B Script Tests</h1>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            {showCreate ? "Cancel" : "New Test"}
          </button>
        </div>

        {/* Create Form */}
        {showCreate && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 mb-6">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">Create A/B Test</h2>
            <div className="space-y-4">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Test name"
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
              />
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Variant A</label>
                  <textarea
                    value={variantA}
                    onChange={(e) => setVariantA(e.target.value)}
                    rows={4}
                    className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                    placeholder="First script variant..."
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">Variant B</label>
                  <textarea
                    value={variantB}
                    onChange={(e) => setVariantB(e.target.value)}
                    rows={4}
                    className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white text-sm"
                    placeholder="Second script variant..."
                  />
                </div>
              </div>
              <button
                onClick={createTest}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Create Test
              </button>
            </div>
          </div>
        )}

        {/* Selected test detail */}
        {selectedTest && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 mb-6">
            <div className="flex justify-between items-start mb-4">
              <h2 className="text-lg font-semibold dark:text-white">{selectedTest.name}</h2>
              <button onClick={() => setSelectedTest(null)} className="text-gray-400 hover:text-gray-600">
                Close
              </button>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                <div className="flex justify-between mb-2">
                  <span className="font-semibold text-blue-700 dark:text-blue-400">Variant A</span>
                  <span className="text-sm text-gray-500">
                    {selectedTest.results.a.count} tests |
                    Avg: {selectedTest.results.a.avg_score?.toFixed(1) || "N/A"}
                  </span>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {selectedTest.variant_a}
                </p>
              </div>
              <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
                <div className="flex justify-between mb-2">
                  <span className="font-semibold text-green-700 dark:text-green-400">Variant B</span>
                  <span className="text-sm text-gray-500">
                    {selectedTest.results.b.count} tests |
                    Avg: {selectedTest.results.b.avg_score?.toFixed(1) || "N/A"}
                  </span>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {selectedTest.variant_b}
                </p>
              </div>
            </div>
            {/* Winner indicator */}
            {selectedTest.results.a.avg_score && selectedTest.results.b.avg_score && (
              <div className="mt-4 text-center">
                <span className={`text-lg font-bold ${
                  selectedTest.results.a.avg_score > selectedTest.results.b.avg_score
                    ? "text-blue-600" : "text-green-600"
                }`}>
                  Variant {selectedTest.results.a.avg_score > selectedTest.results.b.avg_score ? "A" : "B"} is winning!
                </span>
              </div>
            )}
          </div>
        )}

        {/* Tests list */}
        <div className="space-y-3">
          {tests.length === 0 && !showCreate && (
            <div className="text-center py-12 text-gray-400">
              No A/B tests yet. Create one to compare script variants.
            </div>
          )}
          {tests.map((test) => (
            <button
              key={test.id}
              onClick={() => fetchTestDetail(test.id)}
              className="w-full text-left bg-white dark:bg-gray-800 rounded-xl shadow p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium dark:text-white">{test.name}</h3>
                  <p className="text-xs text-gray-500 mt-1">
                    Created: {new Date(test.created_at).toLocaleDateString()}
                  </p>
                </div>
                <span className={`px-2 py-1 text-xs rounded-full ${
                  test.is_active
                    ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                }`}>
                  {test.is_active ? "Active" : "Inactive"}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
