import { ReactNode } from 'react'

export const COLOR = { EDGE: '#2563eb', IDL: '#ea580c', OT: '#0d9488', IOL: '#7c3aed', OTRO: '#64748b', jugador: '#dc2626' }
export const grupoColor = (g?: string | null) => (g && (COLOR as any)[g]) || COLOR.OTRO

export const pct = (v?: number | null, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`)
export const num = (v?: number | null, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d))
export const int = (v?: number | null) => (v === null || v === undefined ? '—' : Math.round(v).toLocaleString('es-MX'))
export const pval = (p?: number | null) => (p === null || p === undefined ? '—' : p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`)
export const altura = (inches?: number | null) => (inches ? `${Math.floor(inches / 12)}'${Math.round(inches % 12)}" (${(inches * 2.54).toFixed(0)} cm)` : '—')

export function Card({ title, subtitle, children, right, className = '' }: { title?: ReactNode; subtitle?: ReactNode; children: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`}>
      {(title || right) && (
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-slate-800">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Kpi({ label, value, sub, tone = 'slate', help }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'slate' | 'green' | 'red' | 'blue'; help?: string }) {
  const tones = { slate: 'text-slate-900', green: 'text-emerald-700', red: 'text-rose-700', blue: 'text-blue-700' }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm" title={help}>
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${tones[tone]}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  )
}

export function Select<T extends string | number>({ label, value, onChange, options, className = '' }: { label: string; value: T | ''; onChange: (v: string) => void; options: { value: T | ''; label: string }[]; className?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-xs font-medium text-slate-600 ${className}`}>
      {label}
      <select className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-900 focus:border-blue-500 focus:outline-none" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => <option key={String(o.value)} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

export function Badge({ children, color = 'slate' }: { children: ReactNode; color?: 'slate' | 'green' | 'red' | 'amber' | 'blue' | 'violet' }) {
  const c = {
    slate: 'bg-slate-100 text-slate-700', green: 'bg-emerald-100 text-emerald-800', red: 'bg-rose-100 text-rose-800',
    amber: 'bg-amber-100 text-amber-800', blue: 'bg-blue-100 text-blue-800', violet: 'bg-violet-100 text-violet-800',
  }
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${c[color]}`}>{children}</span>
}

export function Note({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warn' }) {
  const c = tone === 'warn' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-slate-200 bg-slate-50 text-slate-600'
  return <div className={`rounded-lg border px-3 py-2 text-xs leading-relaxed ${c}`}>{children}</div>
}

export function Loading({ text = 'Cargando…' }: { text?: string }) {
  return <div className="flex items-center gap-2 p-6 text-sm text-slate-500"><span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />{text}</div>
}

export function ErrorBox({ error }: { error: string }) {
  return <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">No se pudieron cargar los datos: {error}</div>
}

/** Histograma simple a partir de valores crudos. */
export function histogram(values: number[], bins = 12, min?: number, max?: number) {
  const v = values.filter((x) => x !== null && !Number.isNaN(x))
  if (!v.length) return []
  const lo = min ?? Math.min(...v)
  const hi = max ?? Math.max(...v)
  const w = (hi - lo) / bins || 1
  const out = Array.from({ length: bins }, (_, i) => ({ x0: lo + i * w, x1: lo + (i + 1) * w, mid: lo + (i + 0.5) * w, n: 0 }))
  for (const x of v) out[Math.min(bins - 1, Math.max(0, Math.floor((x - lo) / w)))].n++
  return out
}

export function PercentileBar({ value }: { value?: number | null }) {
  if (value === null || value === undefined) return <span className="text-xs text-slate-400">—</span>
  const color = value >= 75 ? 'bg-emerald-500' : value <= 25 ? 'bg-rose-500' : 'bg-blue-500'
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-24 rounded-full bg-slate-200">
        <div className={`absolute left-0 top-0 h-2 rounded-full ${color}`} style={{ width: `${Math.max(2, value)}%` }} />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-slate-600">{value.toFixed(0)}</span>
    </div>
  )
}
