import { num, pval } from './ui'

/** Forest plot de odds ratios en escala logarítmica, dibujado con CSS. */
export function Forest({ rows, min, max }: { rows: { etiqueta: string; OR: number; lo: number; hi: number; p?: number | null }[]; min?: number; max?: number }) {
  const lo = Math.min(min ?? 0.5, ...rows.map((r) => r.lo))
  const hi = Math.max(max ?? 2, ...rows.map((r) => r.hi))
  const L = Math.log(lo * 0.95)
  const H = Math.log(hi * 1.05)
  const x = (v: number) => ((Math.log(v) - L) / (H - L)) * 100
  const ticks = [0.5, 0.75, 1, 1.5, 2, 3].filter((t) => t >= lo * 0.95 && t <= hi * 1.05)
  return (
    <div className="text-xs">
      {rows.map((r) => {
        const sig = r.lo > 1 || r.hi < 1
        const color = !sig ? '#94a3b8' : r.OR > 1 ? '#047857' : '#be123c'
        return (
          <div key={r.etiqueta} className="grid grid-cols-[minmax(0,13rem)_1fr_7.5rem] items-center gap-2 border-b border-slate-100 py-1">
            <div className="truncate text-slate-700" title={r.etiqueta}>{r.etiqueta}</div>
            <div className="relative h-4">
              <div className="absolute top-0 h-4 w-px bg-slate-400" style={{ left: `${x(1)}%` }} />
              <div className="absolute top-[7px] h-0.5" style={{ left: `${x(r.lo)}%`, width: `${x(r.hi) - x(r.lo)}%`, background: color }} />
              <div className="absolute top-[3px] h-2.5 w-2.5 -translate-x-1/2 rounded-full" style={{ left: `${x(r.OR)}%`, background: color }} />
            </div>
            <div className="text-right tabular-nums text-slate-600"><b className="text-slate-800">{num(r.OR)}</b> [{num(r.lo)}–{num(r.hi)}]{r.p !== undefined && <div className="text-[10px] text-slate-400">{pval(r.p)}</div>}</div>
          </div>
        )
      })}
      <div className="grid grid-cols-[minmax(0,13rem)_1fr_7.5rem] gap-2 pt-1">
        <div />
        <div className="relative h-4 text-[10px] text-slate-400">{ticks.map((t) => <span key={t} className="absolute -translate-x-1/2" style={{ left: `${x(t)}%` }}>{t}</span>)}</div>
        <div className="text-right text-[10px] text-slate-400">OR [IC95]</div>
      </div>
    </div>
  )
}
