interface TradingViewWidgetProps {
  title: string
  symbol: string
  interval?: string
}

export default function TradingViewWidget({ title, symbol, interval = '5' }: TradingViewWidgetProps) {
  const src = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}&theme=dark&style=1&locale=en&toolbarbg=%230d1117&saveimage=0&hide_top_toolbar=true`

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-950 overflow-hidden shadow-lg shadow-black/20">
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-slate-800 bg-slate-900/80">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          <div className="text-xs text-slate-500">{symbol}</div>
        </div>
      </div>
      <div className="h-72 bg-black">
        <iframe
          title={`tv-widget-${symbol}`}
          src={src}
          className="h-full w-full border-0"
          loading="lazy"
          sandbox="allow-scripts allow-same-origin allow-popups"
          referrerPolicy="no-referrer"
        />
      </div>
    </div>
  )
}
