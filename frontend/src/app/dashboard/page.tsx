"use client";

export default function Dashboard() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Dashboard
            </h1>
            <nav className="flex gap-4">
              <a href="/dashboard" className="text-sm font-medium text-brand-600">Overview</a>
              <a href="/dashboard/competitors" className="text-sm font-medium text-gray-500 hover:text-gray-700">Competitors</a>
              <a href="/dashboard/content" className="text-sm font-medium text-gray-500 hover:text-gray-700">Content</a>
              <a href="/dashboard/reports" className="text-sm font-medium text-gray-500 hover:text-gray-700">Reports</a>
            </nav>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Stats cards */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard title="Competitors" value="—" description="Being tracked" />
          <StatsCard title="Reports" value="—" description="This month" />
          <StatsCard title="Content Tasks" value="—" description="In pipeline" />
          <StatsCard title="Plan" value="—" description="Current subscription" />
        </div>

        {/* Placeholder sections */}
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Competitor Activity</h2>
            <p className="mt-2 text-sm text-gray-500">Activity charts will be displayed here.</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Reports</h2>
            <p className="mt-2 text-sm text-gray-500">Latest digests and alerts will appear here.</p>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatsCard({ title, value, description }: { title: string; value: string; description: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
      <p className="mt-1 text-3xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
    </div>
  );
}
