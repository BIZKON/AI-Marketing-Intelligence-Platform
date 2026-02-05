export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-2xl text-center">
        <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-6xl">
          AI Marketing Intelligence
        </h1>
        <p className="mt-6 text-lg leading-8 text-gray-600 dark:text-gray-400">
          Competitive intelligence and content automation platform for marketers.
          Track competitors, generate insights, and automate content creation.
        </p>
        <div className="mt-10 flex items-center justify-center gap-x-6">
          <a
            href="/dashboard"
            className="rounded-md bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors"
          >
            Go to Dashboard
          </a>
          <a
            href="/api/v1/docs"
            className="text-sm font-semibold leading-6 text-gray-900 dark:text-gray-300"
          >
            API Docs <span aria-hidden="true">&rarr;</span>
          </a>
        </div>
      </div>
    </main>
  );
}
