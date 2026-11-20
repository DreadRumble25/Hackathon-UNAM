import { useEffect, useMemo, useState } from 'react'
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Card, ErrorBox, Loading, Note, grupoColor, num, pct } from '../ui'

type Escenario = { grupo: 'EDGE' | 'IDL'; burst: number; peso: number; dqb: number; nRush: number; tercero: boolean; ytg: number; pa: boolean; shotgun: boolean }

function vector(m: any, s: Escenario, burstOverride?: number): number[] {
  const c = m.centros
  const idl = s.grupo === 'IDL' ? 1 : 0
  const bc = (burstOverride ?? s.burst) - c.burst
  const w10 = (s.peso - c.weight) / 10
  const vals: Record<string, number> = {
    '(intercepto)': 1, burst_c: bc, w10, idl, burst_x_idl: bc * idl, w10_x_idl: w10 * idl,
    dqb_c: s.dqb - c.dqb, n_rush_c: s.nRush - c.n_rush, third_plus: s.tercero ? 1 : 0, ytg_c: s.ytg - c.ytg, pa: s.pa ? 1 : 0, shotgun: s.shotgun ? 1 : 0,
  }
  return m.terminos.map((t: string) => vals[t] ?? 0)
}

function predecir(m: any, x: number[]) {
  const eta = x.reduce((a, v, i) => a + v * m.coef[i], 0)
  let v = 0
  for (let i = 0; i < x.length; i++) for (let j = 0; j < x.length; j++) v += x[i] * m.vcov[i][j] * x[j]
  const se = Math.sqrt(Math.max(v, 0))
  const f = (z: number) => 1 / (1 + Math.exp(-z))
  return { p: f(eta), lo: f(eta - 1.96 * se), hi: f(eta + 1.96 * se), eta }
}

export default function Simulador() {
  const [m, setM] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [s, setS] = useState<Escenario | null>(null)
  const [jug, setJug] = useState('')

  useEffect(() => {
    api('modelo').then((d) => {
      setM(d)
      const g = d.grupos.EDGE
      setS({ grupo: 'EDGE', burst: g.burst_pct['50'], peso: Math.round(g.peso_media), dqb: Number(g.dqb_media.toFixed(1)), nRush: 4, tercero: false, ytg: 10, pa: false, shotgun: true })
    }).catch((e) => setError(e.message))
  }, [])

  const res = useMemo(() => (m && s ? predecir(m, vector(m, s)) : null), [m, s])
  const curva = useMemo(() => {
    if (!m || !s) return []
    const g = m.grupos[s.grupo]
    const lo = g.burst_pct['2'], hi = g.burst_pct['98']
    return Array.from({ length: 31 }, (_, i) => {
      const b = lo + (i * (hi - lo)) / 30
      const r = predecir(m, vector(m, s, b))
      return { burst: b, p: r.p, banda: [r.lo, r.hi] }
    })
  }, [m, s])
  const base = useMemo(() => (m && s ? predecir(m, vector(m, s, m.grupos[s.grupo].burst_pct['50'])) : null), [m, s])
  const contrib = useMemo(() => {
    if (!m || !s) return []
    const x = vector(m, s)
    return m.terminos.map((t: string, i: number) => ({ t, etiqueta: m.etiquetas[t] ?? t, v: x[i] * m.coef[i] })).filter((r: any) => r.t !== '(intercepto)' && Math.abs(r.v) > 1e-4)
  }, [m, s])

  if (error) return <ErrorBox error={error} />
  if (!m || !s || !res) return <Loading />
  const g = m.grupos[s.grupo]
  const set = (k: keyof Escenario, v: any) => setS({ ...s, [k]: v })
  const cambiarGrupo = (gr: 'EDGE' | 'IDL') => { const G = m.grupos[gr]; setS({ ...s, grupo: gr, burst: G.burst_pct['50'], peso: Math.round(G.peso_media), dqb: Number(G.dqb_media.toFixed(1)) }) }
  const pctBurst = (() => { const qs = [2, 10, 25, 50, 75, 90, 98]; let k = qs[0]; for (const q of qs) if (s.burst >= g.burst_pct[String(q)]) k = q; return k })()
  const diff = res.p - (base?.p ?? res.p)

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 to-white p-5 shadow-sm">
        <div className="text-[11px] font-bold uppercase tracking-wider text-violet-700">Simulador estadístico · modelo M3</div>
        <h2 className="text-lg font-bold text-slate-900">Explora cómo cambia la probabilidad estimada de presión según el perfil del defensor y la situación</h2>
        <p className="mt-1 max-w-4xl text-sm text-slate-600">Usa los coeficientes reales de la regresión logística ajustada con {m.ajuste.n.toLocaleString('es-MX')} rusher-jugadas de {m.ajuste.jugadores} jugadores (tasa base {pct(m.ajuste.tasa_base)}). El intervalo usa la matriz de covarianza robusta por jugador.</p>
      </section>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2" title="Escenario">
          <div className="space-y-4 text-sm">
            <div>
              <label className="text-xs font-medium text-slate-600">Partir del perfil de un jugador</label>
              <select className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" value={jug} onChange={(e) => {
                setJug(e.target.value)
                const p = m.jugadores.find((x: any) => String(x.nflId) === e.target.value)
                if (p) { const G = m.grupos[p.grupo]; setS({ ...s, grupo: p.grupo, burst: p.burst_med, peso: p.peso, dqb: Number(G.dqb_media.toFixed(1)) }) }
              }}>
                <option value="">— Escenario manual —</option>
                {m.jugadores.map((p: any) => <option key={p.nflId} value={p.nflId}>{p.nombre} ({p.pos}, {p.equipo}) · burst {num(p.burst_med)}</option>)}
              </select>
            </div>
            <div className="flex gap-2">{(['EDGE', 'IDL'] as const).map((gr) => (
              <button key={gr} onClick={() => cambiarGrupo(gr)} className="flex-1 rounded-md border px-3 py-1.5 text-sm font-semibold" style={s.grupo === gr ? { background: grupoColor(gr), color: 'white', borderColor: grupoColor(gr) } : { color: grupoColor(gr) }}>{gr}</button>
            ))}</div>
            <Slider label="Burst (velocidad máx. en el 1er segundo)" unit="yd/s" min={g.burst_pct['2']} max={g.burst_pct['98']} step={0.05} value={s.burst} onChange={(v) => set('burst', v)} hint={`≈ percentil ${pctBurst} de los ${s.grupo} · mediana ${num(g.burst_pct['50'])}`} />
            <Slider label="Peso" unit="lb" min={Math.round(g.peso_min)} max={Math.round(g.peso_max)} step={1} value={s.peso} onChange={(v) => set('peso', v)} hint={`media de los ${s.grupo}: ${Math.round(g.peso_media)} lb`} />
            <Slider label="Distancia al QB en el snap" unit="yd" min={Number(g.dqb_min.toFixed(1))} max={Number(g.dqb_max.toFixed(1))} step={0.1} value={s.dqb} onChange={(v) => set('dqb', v)} hint="alineación: más abierto = más lejos" />
            <Slider label="Yardas por avanzar" unit="yd" min={1} max={m.ytg.max} step={1} value={s.ytg} onChange={(v) => set('ytg', v)} />
            <div>
              <label className="text-xs font-medium text-slate-600">Rushers en la jugada</label>
              <div className="mt-1 flex gap-1">{m.n_rush.valores.map((n: number) => <button key={n} onClick={() => set('nRush', n)} className={`flex-1 rounded border px-2 py-1 text-xs ${s.nRush === n ? 'bg-slate-800 text-white' : 'text-slate-700'}`}>{n}{n >= 5 ? ' (blitz)' : ''}</button>)}</div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {([['tercero', '3.er/4.º down'], ['pa', 'Play action'], ['shotgun', 'Shotgun/Empty']] as const).map(([k, l]) => (
                <label key={k} className={`flex cursor-pointer items-center justify-center gap-1 rounded border px-2 py-1.5 ${s[k] ? 'border-violet-400 bg-violet-50 text-violet-800' : 'text-slate-600'}`}><input type="checkbox" className="hidden" checked={s[k] as boolean} onChange={(e) => set(k, e.target.checked)} />{s[k] ? '✓ ' : ''}{l}</label>
              ))}
            </div>
          </div>
        </Card>

        <div className="space-y-4 lg:col-span-3">
          <Card>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div><div className="text-[11px] uppercase text-slate-500">Probabilidad estimada de presión</div><div className="text-4xl font-bold text-violet-700">{pct(res.p)}</div><div className="text-xs text-slate-500">IC95 {pct(res.lo)}–{pct(res.hi)}</div></div>
              <div><div className="text-[11px] uppercase text-slate-500">Presiones esperadas por 100 snaps</div><div className="text-4xl font-bold text-slate-800">{(res.p * 100).toFixed(1)}</div><div className="text-xs text-slate-500">en este escenario repetido</div></div>
              <div><div className="text-[11px] uppercase text-slate-500">vs burst mediano del grupo</div><div className={`text-4xl font-bold ${diff > 0.001 ? 'text-emerald-700' : diff < -0.001 ? 'text-rose-700' : 'text-slate-500'}`}>{diff >= 0 ? '+' : ''}{(diff * 100).toFixed(1)}</div><div className="text-xs text-slate-500">puntos porcentuales (mediana {pct(base?.p)})</div></div>
            </div>
          </Card>
          <Card title="Probabilidad estimada según el burst, con el resto del escenario fijo" subtitle="Banda = IC95 · punto = escenario actual · línea vertical = mediana del grupo">
            <div className="h-64">
              <ResponsiveContainer>
                <ComposedChart data={curva} margin={{ top: 8, right: 12, bottom: 12, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="burst" domain={['dataMin', 'dataMax']} tickFormatter={(v) => Number(v).toFixed(1)} fontSize={10} label={{ value: 'burst (yd/s)', position: 'insideBottom', offset: -6, fontSize: 10 }} />
                  <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={36} domain={[0, 'auto']} />
                  <Tooltip formatter={(v: any) => (Array.isArray(v) ? `${pct(v[0])}–${pct(v[1])}` : pct(Number(v)))} labelFormatter={(v: any) => `${Number(v).toFixed(2)} yd/s`} />
                  <Area dataKey="banda" fill="#8b5cf6" fillOpacity={0.15} stroke="none" isAnimationActive={false} />
                  <Line dataKey="p" stroke="#7c3aed" strokeWidth={2} dot={false} isAnimationActive={false} />
                  <ReferenceLine x={g.burst_pct['50']} stroke="#94a3b8" strokeDasharray="4 4" />
                  <ReferenceDot x={s.burst} y={res.p} r={6} fill="#dc2626" stroke="white" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </Card>
          <Card title="Qué empuja la estimación en este escenario" subtitle="Contribución de cada variable al log-odds, respecto a un jugador y una jugada promedio (barras a la derecha = más presión)">
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={contrib} layout="vertical" margin={{ left: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" fontSize={10} tickFormatter={(v) => Number(v).toFixed(2)} />
                  <YAxis type="category" dataKey="etiqueta" width={190} fontSize={10} interval={0} />
                  <Tooltip formatter={(v: any) => [Number(v).toFixed(3), 'log-odds']} />
                  <ReferenceLine x={0} stroke="#475569" />
                  <Bar dataKey="v">{contrib.map((c: any) => <Cell key={c.t} fill={c.v >= 0 ? '#059669' : '#e11d48'} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
      </div>
      <Note tone="warn">
        El simulador describe asociaciones del modelo: no promete que entrenar el burst o cambiar una alineación producirá esa probabilidad. Fuera del rango observado (2.º–98.º percentil) no hay datos para respaldar la estimación, por eso los controles se limitan a ese rango.
        El modelo discrimina de forma modesta (AUC {num(m.ajuste.auc)}): los valores son promedios para muchas jugadas parecidas, no el pronóstico de una jugada.
      </Note>
    </div>
  )
}

function Slider({ label, unit, min, max, step, value, onChange, hint }: { label: string; unit: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void; hint?: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between"><label className="text-xs font-medium text-slate-600">{label}</label><span className="text-sm font-semibold tabular-nums text-slate-900">{num(value, step < 1 ? 2 : 0)} {unit}</span></div>
      <input type="range" min={min} max={max} step={step} value={Math.min(max, Math.max(min, value))} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-violet-600" />
      {hint && <div className="text-[11px] text-slate-400">{hint}</div>}
    </div>
  )
}
