import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api } from '../api'
import { Badge, Card, ErrorBox, Kpi, Loading, Note, Select, grupoColor, int, num, pct, pval } from '../ui'

const CLASE: Record<string, 'green' | 'red' | 'amber' | 'slate' | 'blue'> = {
  'Por encima (p<0.05)': 'green', 'Por debajo (p<0.05)': 'red', 'Tendencia por encima': 'blue', 'Tendencia por debajo': 'amber', 'Dentro de lo esperado': 'slate',
}

export default function ObservadoEsperado({ onPlayer, equipos }: { onPlayer: (id: number) => void; equipos: string[] }) {
  const [grupo, setGrupo] = useState('TODOS')
  const [min, setMin] = useState('100')
  const [equipo, setEquipo] = useState('')
  const [orden, setOrden] = useState('z_aj')
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api('observado-esperado', { grupo, min_snaps: min, equipo }).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message)) }, [grupo, min, equipo])

  const rows = useMemo(() => {
    const r = [...(data?.jugadores ?? [])]
    const dir = orden === 'nombre' ? 1 : -1
    return r.sort((a: any, b: any) => (orden === 'nombre' ? a.nombre.localeCompare(b.nombre) : dir * ((a[orden] ?? -1e9) - (b[orden] ?? -1e9))))
  }, [data, orden])
  const maxv = useMemo(() => Math.max(0.3, ...rows.map((r: any) => Math.max(r.tasa_esp, r.tasa_model_obs))), [rows])

  if (error) return <ErrorBox error={error} />
  if (!data) return <Loading />
  const s = data.resumen
  return (
    <div className="space-y-4">
      <Card>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Select label="Grupo" value={grupo} onChange={setGrupo} options={[{ value: 'TODOS', label: 'EDGE e IDL' }, { value: 'EDGE', label: 'EDGE (DE, OLB)' }, { value: 'IDL', label: 'IDL (DT, NT)' }]} />
          <Select label="Mínimo de jugadas modelables" value={min} onChange={setMin} options={['25', '50', '100', '150', '200'].map((v) => ({ value: v, label: `≥ ${v}` }))} />
          <Select label="Equipo" value={equipo} onChange={setEquipo} options={[{ value: '', label: 'Todos' }, ...equipos.map((t) => ({ value: t, label: t }))]} />
          <Select label="Ordenar por" value={orden} onChange={setOrden} options={[{ value: 'z_aj', label: 'Evidencia (z ajustado)' }, { value: 'o_e', label: 'Razón O/E' }, { value: 'dif_100', label: 'Diferencia por 100 snaps' }, { value: 'tasa_model_obs', label: 'Tasa observada' }, { value: 'n_model', label: 'Oportunidades' }, { value: 'nombre', label: 'Nombre' }]} />
        </div>
      </Card>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Jugadores evaluados" value={int(s.n)} sub={`≥ ${s.min_snaps} jugadas modelables`} />
        <Kpi label="Por encima (p<0.05)" value={int(s.sobre)} tone="green" sub="O/E > 1 con evidencia" />
        <Kpi label="Por debajo (p<0.05)" value={int(s.bajo)} tone="red" sub="O/E < 1 con evidencia" />
        <Kpi label="Esperados por azar" value={num(s.esperados_por_azar, 1)} sub="5% de los evaluados, en total" />
        <Kpi label="Sobreviven Bonferroni" value={int(s.sobreviven_bonferroni)} sub={`umbral p < ${s.bonferroni ? s.bonferroni.toExponential(1) : '—'}`} />
      </div>
      <Note tone="warn">
        La tasa <b>esperada</b> es lo que el modelo M3 estima para las jugadas reales de cada jugador, dado su burst en cada jugada, su peso, su grupo y el contexto.
        Un O/E alto significa que produce más de lo que esas variables explican. Cuando se evalúan {s.n} jugadores a la vez, alrededor de {num(s.esperados_por_azar, 0)} saldrían «significativos» solo por azar,
        así que esta lista es <b>exploratoria</b>: sirve para decidir a quién revisar en video, no para declarar a un jugador superior. Los p-valores ya corrigen la sobredispersión entre jugadores (φ = {num(s.phi)}).
      </Note>
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2" title="Esperada vs observada" subtitle="Sobre la diagonal: más presión de la esperada · tamaño = oportunidades · clic para abrir el perfil">
          <div className="h-96">
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="tasa_esp" domain={[0, maxv]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} label={{ value: 'esperada por el modelo', position: 'insideBottom', offset: -8, fontSize: 10 }} />
                <YAxis type="number" dataKey="tasa_model_obs" domain={[0, maxv]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={36} />
                <ZAxis type="number" dataKey="n_model" range={[20, 160]} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: maxv, y: maxv }]} stroke="#64748b" strokeDasharray="4 4" />
                <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
                  <div className="rounded border border-slate-200 bg-white p-2 text-xs shadow"><div className="font-semibold">{payload[0].payload.nombre} <span className="text-slate-500">{payload[0].payload.pos} · {payload[0].payload.equipo}</span></div>
                    <div>Observada {pct(payload[0].payload.tasa_model_obs)} · esperada {pct(payload[0].payload.tasa_esp)} · O/E {num(payload[0].payload.o_e)}</div></div>) : null} />
                {['EDGE', 'IDL'].map((g) => <Scatter key={g} name={g} data={rows.filter((r: any) => r.grupo === g)} fill={grupoColor(g)} fillOpacity={0.65} cursor="pointer" onClick={(d: any) => onPlayer(d.nflId ?? d.payload?.nflId)} />)}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="lg:col-span-3" title="Ranking observado contra esperado" subtitle="IC95 de la tasa observada (Wilson) y del O/E (aproximación normal con sobredispersión)">
          <div className="max-h-[440px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-white"><tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-1.5">Jugador</th><th className="text-right">Opor.</th><th className="text-right">Observada [IC95]</th><th className="text-right">Esperada</th><th className="text-right">O/E [IC95]</th><th className="text-right">p</th><th className="pl-2">Lectura</th></tr></thead>
              <tbody>{rows.map((r: any) => (
                <tr key={r.nflId} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onPlayer(r.nflId)}>
                  <td className="py-1"><span className="font-medium text-slate-800">{r.nombre}</span> <span className="text-slate-400">{r.pos} · {r.equipo}</span></td>
                  <td className="text-right tabular-nums">{r.n_model}</td>
                  <td className="text-right tabular-nums">{pct(r.tasa_model_obs)} <span className="text-slate-400">[{pct(r.obs_lo, 0)}–{pct(r.obs_hi, 0)}]</span></td>
                  <td className="text-right tabular-nums">{pct(r.tasa_esp)}</td>
                  <td className="text-right tabular-nums"><b>{num(r.o_e)}</b> <span className="text-slate-400">[{num(r.oe_lo)}–{num(r.oe_hi)}]</span></td>
                  <td className="text-right tabular-nums text-slate-500">{pval(r.p_aj)}</td>
                  <td className="pl-2"><Badge color={CLASE[r.clasificacion]}>{r.clasificacion}</Badge></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}
