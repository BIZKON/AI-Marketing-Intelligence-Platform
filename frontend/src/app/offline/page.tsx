"use client";

export default function OfflinePage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="text-center max-w-md px-6">
        <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-gray-200 dark:bg-gray-800 flex items-center justify-center">
          <svg
            className="w-8 h-8 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M18.364 5.636a9 9 0 010 12.728M5.636 5.636a9 9 0 000 12.728M12 12h.01"
            />
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
          You&apos;re offline
        </h1>
        <p className="text-gray-500 dark:text-gray-400 mb-6">
          Check your internet connection and try again. Your training progress
          is saved and will sync when you&apos;re back online.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="inline-flex items-center px-4 py-2 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-700 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
