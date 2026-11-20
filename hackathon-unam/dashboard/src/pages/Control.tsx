import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Badge, Card, ErrorBox, Kpi, Loading, Note, Select, grupoColor, int, num, pct } from '../ui'

type Filtros = { equipos: string[]; semanas: number[]; partidos: { gameId: number; semana: number; etiqueta: string; equipos: string[] }[]; grupos: { valor: string; etiqueta: string; lado?: string }[] }

const METRICAS: { key: string; label: string; fmt: (v: number) => string; mejor: 'alto' | 'bajo' }[] = [
  { key: 'tasa_presion', label: 'Presión generada (por snap de rush)', fmt: (v) => pct(v), mejor: 'alto' },
  { key: 'oe', label: 'Presión observada / esperada', fmt: (v) => num(v), mejor: 'alto' },
  { key: 'burst_medio', label: 'Burst promedio de rushers (yd/s)', fmt: (v) => num(v), mejor: 'alto' },
  { key: 'efectividad', label: 'Efectividad de bloqueo', fmt: (v) => pct(v), mejor: 'alto' },
  { key: 'presion_permitida', label: 'Dropbacks con presión permitida', fmt: (v) => pct(v), mejor: 'bajo' },
]

const TIPO: Record<string, { label: string; color: 'green' | 'red' | 'amber' | 'blue' | 'violet' }> = {
  fortaleza: { label: 'Fortaleza', color: 'green' },
  revision: { label: 'Revisión técnica', color: 'red' },
  oportunidad: { label: 'Oportunidad', color: 'amber' },
  situacion: { label: 'Situación', color: 'blue' },
  contexto: { label: 'Contexto', color: 'violet' },
}

export default function Control({ onPlayer, onLab }: { onPlayer: (id: number) => void; onLab: () => void }) {
  const [f, setF] = useState<Filtros | null>(null)
  const [equipo, setEquipo] = useState('')
  const [grupo, setGrupo] = useState('TODOS')
  const [semana, setSemana] = useState('')
  const [partido, setPartido] = useState('')
  const [minSnaps, setMinSnaps] = useState('50')
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [metrica, setMetrica] = useState('tasa_presion')

  useEffect(() => { api<Filtros>('filtros').then(setF).catch((e) => setError(e.message)) }, [])
  useEffect(() => {
    setLoading(true)
    api('resumen', { equipo, grupo, semana, partido, min_snaps: minSnaps })
      .then((d) => { setData(d); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [equipo, grupo, semana, partido, minSnaps])

  const partidos = useMemo(() => (f?.partidos ?? []).filter((p) => (!semana || p.semana === Number(semana)) && (!equipo || p.equipos.includes(equipo))), [f, semana, equipo])
  useEffect(() => { if (partido && !partidos.some((p) => String(p.gameId) === partido)) setPartido('') }, [partidos, partido])

  const m = METRICAS.find((x) => x.key === metrica)!
  const teamRows = useMemo(() => {
    const rows = (data?.equipos ?? []).filter((r: any) => r[metrica] !== null && r[metrica] !== undefined)
    return [...rows].sort((a: any, b: any) => (m.mejor === 'alto' ? b[metrica] - a[metrica] : a[metrica] - b[metrica]))
  }, [data, metrica, m])
  const liga = teamRows.length ? teamRows.reduce((s: number, r: any) => s + r[metrica], 0) / teamRows.length : null

  if (error && !data) return <ErrorBox error={error} />
  const k = data?.kpis
  const lado = data?.filtros?.lado_filtrado

  return (
    <div className="space-y-4">
      <Card>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Select label="Equipo" value={equipo} onChange={setEquipo} options={[{ value: '', label: 'Todos los equipos' }, ...(f?.equipos ?? []).map((t) => ({ value: t, label: t }))]} />
          <Select label="Posición" value={grupo} onChange={setGrupo} options={(f?.grupos ?? [{ valor: 'TODOS', etiqueta: 'Todas las posiciones' }]).map((g) => ({ value: g.valor, label: g.etiqueta }))} />
          <Select label="Semana" value={semana} onChange={setSemana} options={[{ value: '', label: 'Semanas 1–8' }, ...(f?.semanas ?? []).map((s) => ({ value: String(s), label: `Semana ${s}` }))]} />
          <Select label="Partido" value={partido} onChange={setPartido} options={[{ value: '', label: 'Todos los partidos' }, ...partidos.map((p) => ({ value: String(p.gameId), label: p.etiqueta }))]} />
          <Select label="Mínimo de oportunidades" value={minSnaps} onChange={setMinSnaps} options={['1', '10', '25', '50', '100', '150'].map((v) => ({ value: v, label: `≥ ${v} snaps` }))} />
        </div>
        {lado && <p className="mt-2 text-xs text-slate-500">El filtro de posición se aplica a la {lado}; las métricas del otro lado de la pelota incluyen a todos sus jugadores.</p>}
      </Card>

      {!data ? <Loading /> : (
        <div className={loading ? 'opacity-60 transition-opacity' : ''}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kpi label="Jugadores analizados" value={int(k.jugadores)} sub={`con ≥ ${data.filtros.min_snaps} oportunidades (de ${int(k.jugadores_total)})`} />
            <Kpi label="Jugadas disponibles" value={int(k.jugadas)} sub="dropbacks con datos PFF y tracking" />
            <Kpi label="Enfrentamientos" value={int(k.enfrentamientos)} sub="bloqueador × defensor asignado (PFF)" />
            <Kpi label="Explosividad inicial promedio" value={`${num(k.burst_medio)} yd/s`} sub={`liga: ${num(k.liga.burst_medio)} yd/s · EDGE e IDL`} tone="blue" />
            <Kpi label="Presión generada" value={pct(k.tasa_presion)} sub={<>IC95 {pct(k.tasa_presion_lo)}–{pct(k.tasa_presion_hi)} · liga {pct(k.liga.tasa_presion)}<br />{int(k.presiones)} presiones en {int(k.rush_snaps)} snaps de rush</>}
              tone={k.tasa_presion > k.liga.tasa_presion ? 'green' : 'slate'} />
            <Kpi label="Observada / esperada" value={num(k.oe)} sub={`esperada por el modelo: ${pct(k.tasa_esperada)} (EDGE e IDL)`} tone={k.oe >= 1.1 ? 'green' : k.oe <= 0.9 ? 'red' : 'slate'}
              help="Suma de presiones reales dividida entre la suma de probabilidades del modelo logístico para esas mismas jugadas" />
            <Kpi label="Presión permitida" value={pct(k.presion_permitida)} sub={`de ${int(k.dropbacks)} dropbacks con ≥1 presión · liga ${pct(k.liga.presion_permitida)}`}
              tone={k.presion_permitida > k.liga.presion_permitida ? 'red' : 'green'} />
            <Kpi label="Efectividad de bloqueo" value={pct(k.efectividad)} sub={`IC95 ${pct(k.efectividad_lo)}–${pct(k.efectividad_hi)} · liga ${pct(k.liga.efectividad)} · ${int(k.block_snaps)} bloqueos`}
              tone={k.efectividad >= k.liga.efectividad ? 'green' : 'red'} help="1 − (bloqueos con presión permitida o 'beaten by defender') / bloqueos" />
          </div>

          <Hallazgo h={data.hallazgo} onLab={onLab} />

          <div className="mt-4 grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3" title="Comparación entre equipos" subtitle="Mismos filtros de semana, partido y posición; la línea punteada es el promedio de los equipos"
              right={<select className="rounded-md border border-slate-300 px-2 py-1 text-xs" value={metrica} onChange={(e) => setMetrica(e.target.value)}>{METRICAS.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</select>}>
              <div className="h-[420px]">
                <ResponsiveContainer>
                  <BarChart data={teamRows} layout="vertical" margin={{ left: 8, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(v) => (metrica === 'oe' || metrica === 'burst_medio' ? Number(v).toFixed(2) : `${(v * 100).toFixed(0)}%`)} fontSize={11} domain={metrica === 'oe' || metrica === 'burst_medio' ? ['auto', 'auto'] : [0, 'auto']} />
                    <YAxis type="category" dataKey="equipo" width={40} fontSize={11} interval={0} />
                    <Tooltip formatter={(v: any) => m.fmt(Number(v))} />
                    {liga !== null && <ReferenceLine x={liga} stroke="#475569" strokeDasharray="4 4" />}
                    <Bar dataKey={metrica} name={m.label}>
                      {teamRows.map((r: any) => <Cell key={r.equipo} fill={r.equipo === equipo ? '#dc2626' : '#94a3b8'} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {equipo && (() => {
                const r = teamRows.findIndex((x: any) => x.equipo === equipo)
                return r >= 0 ? <p className="text-xs text-slate-600"><b>{equipo}</b> ocupa el lugar <b>{r + 1}</b> de {teamRows.length} en «{m.label}» ({m.fmt(teamRows[r][metrica])}).</p> : null
              })()}
            </Card>
            <Card className="lg:col-span-2" title="Observaciones automáticas" subtitle="Generadas con reglas fijas sobre los datos filtrados; ninguna es una conclusión causal">
              <ul className="max-h-[460px] space-y-2 overflow-y-auto pr-1">
                {data.observaciones.length === 0 && <li className="text-sm text-slate-500">No hay suficientes datos con estos filtros.</li>}
                {data.observaciones.map((o: any, i: number) => (
                  <li key={i} className={`rounded-lg border border-slate-200 p-2.5 ${o.nflId ? 'cursor-pointer hover:border-blue-300 hover:bg-blue-50/40' : ''}`} onClick={() => o.nflId && onPlayer(o.nflId)}>
                    <div className="mb-1 flex items-center gap-2"><Badge color={TIPO[o.tipo]?.color ?? 'slate'}>{TIPO[o.tipo]?.label ?? o.tipo}</Badge><span className="text-xs font-semibold text-slate-700">{o.titulo}</span></div>
                    <p className="text-xs leading-relaxed text-slate-600">{o.texto}</p>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Generadores de presión" subtitle={`Ordenados por tasa ajustada por tamaño de muestra · ≥ ${data.filtros.min_snaps} snaps de rush`}>
              <PlayerTable rows={data.top_rushers} onPlayer={onPlayer} cols={[
                ['snaps', 'Snaps', int], ['presiones', 'Pres.', int], ['tasa', 'Obs.', pct], ['tasa_esp', 'Esp.', pct], ['o_e', 'O/E', num], ['tasa_ajustada', 'Ajust.', pct], ['burst_med', 'Burst', num],
              ]} />
            </Card>
            <Card title="Bloqueadores más efectivos" subtitle={`Ordenados por efectividad ajustada por tamaño de muestra · ≥ ${data.filtros.min_snaps} bloqueos`}>
              <PlayerTable rows={data.top_bloqueadores} onPlayer={onPlayer} cols={[
                ['snaps', 'Bloq.', int], ['permitidas', 'Pres. perm.', int], ['perdidos', 'Perdidos', int], ['efectividad', 'Efect.', pct], ['efectividad_ajustada', 'Ajust.', pct],
              ]} />
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}

function PlayerTable({ rows, cols, onPlayer }: { rows: any[]; cols: [string, string, (v: any) => string][]; onPlayer: (id: number) => void }) {
  if (!rows?.length) return <p className="text-sm text-slate-500">Sin jugadores que cumplan el mínimo de oportunidades.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1.5">Jugador</th>{cols.map(([k, l]) => <th key={k} className="py-1.5 text-right">{l}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.nflId} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onPlayer(r.nflId)}>
              <td className="py-1.5"><span className="font-medium text-slate-800">{r.nombre}</span> <span className="text-slate-400">{r.pos} · {r.equipo}</span></td>
              {cols.map(([k, , f]) => <td key={k} className="py-1.5 text-right tabular-nums">{f(r[k])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Hallazgo({ h, onLab }: { h: any; onLab: () => void }) {
  const e = h.efectos
  const p = (g: string, q: number) => h.percentiles_prob.find((x: any) => x.grupo === g && x.percentil === q)
  return (
    <section className="mt-4 overflow-hidden rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-blue-100 px-5 py-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-blue-700">Hallazgo principal</div>
          <h2 className="text-lg font-bold text-slate-900">La explosividad en el primer segundo tras el snap está asociada con más presión al QB</h2>
          <p className="text-xs text-slate-600">Burst = velocidad máxima del defensor durante el primer segundo después del snap (10 frames a 10 Hz).</p>
        </div>
        <button onClick={onLab} className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700">Abrir laboratorio de explosividad →</button>
      </div>
      <div className="grid gap-4 p-5 md:grid-cols-3">
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-700">Tasas observadas por quintil de burst</div>
          <div className="flex items-end gap-4">
            <div><div className="text-3xl font-bold text-slate-500">{pct(h.original.q1)}</div><div className="text-[11px] text-slate-500">quintil más bajo</div></div>
            <div className="pb-2 text-slate-400">→</div>
            <div><div className="text-3xl font-bold text-blue-700">{pct(h.original.q5)}</div><div className="text-[11px] text-slate-500">quintil más alto</div></div>
          </div>
          <p className="mt-1 text-xs text-slate-600"><b>{num(h.original.razon, 1)}×</b> más presión · análisis exploratorio, {int(h.original.n)} snaps de rush.</p>
          <p className="mt-1 text-xs text-slate-500">Con la población del modelo (EDGE e IDL, {int(h.modelo.n)} snaps): {pct(h.modelo.q1)} → {pct(h.modelo.q5)} ({num(h.modelo.razon, 1)}×).</p>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-700">Regresión logística (controla peso, posición y contexto)</div>
          <table className="w-full text-xs">
            <tbody>
              <tr><td className="py-0.5 text-slate-600">EDGE, +1 yd/s</td><td className="text-right font-semibold">OR {num(e.edge_yd.OR)}</td><td className="text-right text-slate-500">[{num(e.edge_yd.lo)}–{num(e.edge_yd.hi)}]</td></tr>
              <tr><td className="py-0.5 text-slate-600">IDL, +1 yd/s</td><td className="text-right font-semibold">OR {num(e.idl_yd.OR)}</td><td className="text-right text-slate-500">[{num(e.idl_yd.lo)}–{num(e.idl_yd.hi)}]</td></tr>
              <tr><td className="py-0.5 text-slate-600">EDGE, +1 DE</td><td className="text-right font-semibold">OR {num(e.edge_sd.OR)}</td><td className="text-right text-slate-500">[{num(e.edge_sd.lo)}–{num(e.edge_sd.hi)}]</td></tr>
              <tr><td className="py-0.5 text-slate-600">IDL, +1 DE</td><td className="text-right font-semibold">OR {num(e.idl_sd.OR)}</td><td className="text-right text-slate-500">[{num(e.idl_sd.lo)}–{num(e.idl_sd.hi)}]</td></tr>
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-slate-500">p &lt; 0.001 en ambos grupos; IC95 robustos agrupados por jugador. Medido en desviaciones estándar, el efecto es prácticamente igual en EDGE e IDL. Peso sin efecto propio (EDGE OR {num(e.peso_edge.OR, 3)} por +10 lb).</p>
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold text-slate-700">Probabilidad estimada de presión por jugada</div>
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left font-medium">Grupo</th><th className="text-right font-medium">P10</th><th className="text-right font-medium">P50</th><th className="text-right font-medium">P90</th></tr></thead>
            <tbody>
              {['EDGE', 'IDL'].map((g) => (
                <tr key={g}><td className="py-0.5 font-semibold" style={{ color: grupoColor(g) }}>{g}</td>{[10, 50, 90].map((q) => <td key={q} className="text-right tabular-nums">{pct(p(g, q)?.p)}</td>)}</tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[11px] text-slate-500">Percentiles de burst dentro de cada grupo, con peso y contexto en su promedio. Son estimaciones del modelo, no tasas observadas.</p>
        </div>
      </div>
      <div className="px-5 pb-4"><Note tone="warn">Asociación, no causalidad: el burst también depende del plan de bloqueo, stunts y asignaciones que no están en los datos. El modelo discrimina de forma modesta (AUC {num(h.ajuste.auc)}), así que sirve para comparar promedios, no para predecir una jugada.</Note></div>
    </section>
  )
}
