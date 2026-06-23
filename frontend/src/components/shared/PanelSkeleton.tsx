export default function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="animate-pulse flex flex-col gap-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div 
          key={i} 
          className="h-4 bg-slate-800 rounded" 
          style={{ width: `${Math.max(40, Math.random() * 100)}%` }}
        />
      ))}
    </div>
  )
}
