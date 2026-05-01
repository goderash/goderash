export default function Loading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 w-48 rounded bg-ink-800" />
      <div className="h-4 w-64 rounded bg-ink-800" />
      <div className="rounded-xl border border-ink-800 p-6 space-y-4">
        <div className="h-4 w-24 rounded bg-ink-800" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-3 w-full rounded bg-ink-800/60" />
        ))}
      </div>
    </div>
  )
}
