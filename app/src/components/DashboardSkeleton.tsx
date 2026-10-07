export function DashboardSkeleton() {
  return (
    <main className="page">
      <div className="skeleton skeleton-title" />
      <div className="kpi-row">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card skeleton-card" />
        ))}
      </div>
      <div className="chart-grid">
        <div className="card span-1 skeleton-card tall" />
        <div className="card span-1 skeleton-card tall" />
        <div className="card span-2 skeleton-card tall" />
      </div>
    </main>
  );
}
