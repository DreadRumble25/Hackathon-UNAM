import { useEffect, useMemo, useState } from 'react'
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api } from '../api'
import { Card, ErrorBox, Loading, Note, COLOR, grupoColor, int, num, pct, pval } from '../ui'
import { Forest } from '../charts'

const POS_COLOR: Record<string, string> = { DE: '#1d4ed8', OLB: '#60a5fa', DT: '#c2410c', NT: '#fb923c' }

export default function Laboratorio({ onPlayer }: { onPlayer: (id: number) => void }) {
  const [lab, setLab] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [nivel, setNivel] = useState<'quintiles' | 'deciles'>('deciles')
  useEffect(() => { api('laboratorio').then(setLab).catch((e) => setError(e.message)) }, [])

  const curva = useMemo(() => {
    if (!lab) return {}
    const out: Record<string, any[]> = {}
    for (const g of ['EDGE', 'IDL']) {
      out[g] = lab.curvas[g].map((p: any) => ({ burst: p.burst, p: p.p, banda: [p.lo, p.hi] }))
    }
    return out
  }, [lab])
  const obsPts = useMemo(() => {
    if (!lab) return {}
    const out: Record<string, any[]> = {}
    for (const g of ['EDGE', 'IDL']) out[g] = lab.deciles_grupo[g].map((d: any) => ({ burst: (d.lo + d.hi) / 2, tasa: d.tasa, err: [d.tasa - d.ic_lo, d.ic_hi - d.tasa], n: d.n }))
    return out
  }, [lab])

  if (error) return <ErrorBox error={error} />
  if (!lab) return <Loading text="Cargando laboratorio…" />
  const ef = lab.efectos
  const [A, B, C] = lab.quintiles_versiones
  const comp = A.quintiles.map((q: any, i: number) => ({ q: `Q${q.q}`, A: q.tasa, C: C.quintiles[i]?.tasa, errA: [q.tasa - q.ic_lo, q.ic_hi - q.tasa], errC: C.quintiles[i] ? [C.quintiles[i].tasa - C.quintiles[i].ic_lo, C.quintiles[i].ic_hi - C.quintiles[i].tasa] : [0, 0] }))
  const tabla = nivel === 'deciles' ? lab.deciles_grupo : lab.quintiles_grupo
  const barras = tabla.EDGE.map((d: any, i: number) => ({
    k: `${nivel === 'deciles' ? 'D' : 'Q'}${d.q}`, EDGE: d.tasa, IDL: tabla.IDL[i]?.tasa,
    errE: [d.tasa - d.ic_lo, d.ic_hi - d.tasa], errI: tabla.IDL[i] ? [tabla.IDL[i].tasa - tabla.IDL[i].ic_lo, tabla.IDL[i].ic_hi - tabla.IDL[i].tasa] : [0, 0],
    rE: `${num(d.lo)}–${num(d.hi)}`, rI: tabla.IDL[i] ? `${num(tabla.IDL[i].lo)}–${num(tabla.IDL[i].hi)}` : '',
  }))
  const disp = lab.dispersion
  const alt = lab.metricas_alternativas
  const forestMain = lab.forest
  const ed = lab.entre_dentro.map((r: any) => ({ etiqueta: `${r.componente} · ${r.grupo}`, ...r }))

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-white p-5 shadow-sm">
        <div className="text-[11px] font-bold uppercase tracking-wider text-blue-700">Laboratorio de explosividad</div>
        <h2 className="text-lg font-bold text-slate-900">¿Cuánto se asocia la explosividad del primer segundo con la presión al QB?</h2>
        <p className="mt-1 max-w-4xl text-sm text-slate-600">
          <b>Burst</b> es la velocidad máxima del defensor en el primer segundo tras el snap. Las <b>tasas observadas</b> salen de contar presiones (hurry, hit o sack de PFF) en cada grupo de jugadas.
          Las <b>probabilidades estimadas</b> salen de una regresión logística que además controla peso, grupo y contexto de la jugada. Ambas miden asociación: no prueban que aumentar el burst produzca más presión.
        </p>
      </section>

      <Card title="1. Quintil inferior vs superior: verificación de poblaciones" subtitle="El análisis exploratorio original y la población del modelo no son idénticas; aquí se comparan con los mismos cortes por quintil">
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="space-y-2 lg:col-span-2">
            {[A, B, C].map((v: any) => (
              <div key={v.clave} className={`rounded-lg border p-3 ${v.clave === 'A' ? 'border-blue-300 bg-blue-50/50' : 'border-slate-200'}`}>
                <div className="flex items-baseline justify-between"><span className="text-xs font-semibold text-slate-800">{v.clave}. {v.nombre}</span><span className="text-[11px] text-slate-500">{int(v.n)} snaps · {v.jugadores} jugadores</span></div>
                <div className="mt-1 flex items-baseline gap-2 text-sm"><span className="font-bold text-slate-500">{pct(v.q1)}</span><span className="text-slate-400">→</span><span className="font-bold text-blue-700">{pct(v.q5)}</span><span className="text-xs text-slate-600">({num(v.razon, 2)}×)</span></div>
                <p className="mt-1 text-[11px] text-slate-500">{v.descripcion}</p>
              </div>
            ))}
            <Note>
              La cifra destacada (A: {pct(A.q1)} → {pct(A.q5)}, {num(A.razon, 1)}×) es la del análisis exploratorio original. Al restringir a EDGE e IDL con datos completos (B), la razón baja a {num(B.razon, 2)}×; cambiar la definición de burst (C) casi no la mueve.
              La diferencia viene sobre todo de excluir a linebackers y defensivos secundarios en blitz, que presionan más. La asociación se mantiene en las tres versiones.
            </Note>
          </div>
          <div className="h-80 lg:col-span-3">
            <ResponsiveContainer>
              <BarChart data={comp}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="q" fontSize={11} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={11} width={38} />
                <Tooltip formatter={(v: any) => pct(Number(v))} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="A" name="A · exploratorio original" fill="#93c5fd"><ErrorBar dataKey="errA" width={4} stroke="#1e3a8a" /></Bar>
                <Bar dataKey="C" name="C · población del modelo" fill="#1d4ed8"><ErrorBar dataKey="errC" width={4} stroke="#0f172a" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="2. Tasa de presión observada por nivel de burst" subtitle="Cortes dentro de cada grupo (EDGE e IDL tienen distribuciones distintas) · barras de error = IC95 de Wilson"
          right={<div className="flex rounded-md border border-slate-300 text-xs">{(['quintiles', 'deciles'] as const).map((n) => <button key={n} onClick={() => setNivel(n)} className={`px-2 py-1 ${nivel === n ? 'bg-slate-800 text-white' : 'text-slate-600'}`}>{n}</button>)}</div>}>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={barras}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="k" fontSize={11} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={11} width={38} />
                <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
                  <div className="rounded border border-slate-200 bg-white p-2 text-xs shadow">
                    <div className="font-semibold">{payload[0].payload.k}</div>
                    <div style={{ color: COLOR.EDGE }}>EDGE: {pct(payload[0].payload.EDGE)} · burst {payload[0].payload.rE} yd/s</div>
                    <div style={{ color: COLOR.IDL }}>IDL: {pct(payload[0].payload.IDL)} · burst {payload[0].payload.rI} yd/s</div>
                  </div>) : null} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="EDGE" fill={COLOR.EDGE}><ErrorBar dataKey="errE" width={3} stroke="#0f172a" /></Bar>
                <Bar dataKey="IDL" fill={COLOR.IDL}><ErrorBar dataKey="errI" width={3} stroke="#0f172a" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-600">
            EDGE: {pct(tabla.EDGE[0].tasa)} en el {nivel === 'deciles' ? 'decil' : 'quintil'} más bajo a {pct(tabla.EDGE.at(-1).tasa)} en el más alto.
            IDL: {pct(tabla.IDL[0].tasa)} a {pct(tabla.IDL.at(-1).tasa)}. El aumento es casi monótono en ambos grupos.
          </p>
        </Card>

        <Card title="3. Probabilidad estimada por el modelo logístico" subtitle="Línea: probabilidad estimada con peso y contexto en su promedio · banda: IC95 · puntos: tasa observada por decil">
          <div className="grid grid-cols-2 gap-2">
            {(['EDGE', 'IDL'] as const).map((g) => (
              <div key={g} className="h-64">
                <div className="text-center text-xs font-semibold" style={{ color: grupoColor(g) }}>{g}</div>
                <ResponsiveContainer>
                  <ComposedChart margin={{ top: 4, right: 8, left: 0, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" dataKey="burst" domain={['dataMin', 'dataMax']} tickFormatter={(v) => Number(v).toFixed(1)} fontSize={10} label={{ value: 'burst (yd/s)', position: 'insideBottom', offset: -4, fontSize: 10 }} />
                    <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} domain={[0, 'auto']} />
                    <Tooltip formatter={(v: any, n: any) => (Array.isArray(v) ? `${pct(v[0])}–${pct(v[1])}` : pct(Number(v)))} labelFormatter={(v: any) => `${Number(v).toFixed(2)} yd/s`} />
                    <Area data={curva[g]} dataKey="banda" name="IC95" fill={grupoColor(g)} fillOpacity={0.15} stroke="none" isAnimationActive={false} />
                    <Line data={curva[g]} dataKey="p" name="Estimada" stroke={grupoColor(g)} strokeWidth={2} dot={false} isAnimationActive={false} />
                    <Scatter data={obsPts[g]} dataKey="tasa" name="Observada (decil)" fill="#0f172a"><ErrorBar dataKey="err" width={0} stroke="#64748b" direction="y" /></Scatter>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            ))}
          </div>
          <table className="mt-3 w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left font-medium">Percentil de burst en su grupo</th>{[10, 25, 50, 75, 90].map((q) => <th key={q} className="text-right font-medium">P{q}</th>)}</tr></thead>
            <tbody>{['EDGE', 'IDL'].map((g) => (
              <tr key={g} className="border-t border-slate-100"><td className="py-1 font-semibold" style={{ color: grupoColor(g) }}>{g}</td>
                {[10, 25, 50, 75, 90].map((q) => { const p = lab.percentiles_prob.find((x: any) => x.grupo === g && x.percentil === q); return <td key={q} className="text-right tabular-nums" title={`burst ${num(p.burst)} yd/s · IC95 ${pct(p.lo)}–${pct(p.hi)}`}>{pct(p.p)}</td> })}
              </tr>))}</tbody>
          </table>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1" title="4. EDGE vs IDL" subtitle="Odds ratios del modelo M3 con IC95 robustos por jugador">
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left font-medium">Efecto</th><th className="text-right font-medium">OR</th><th className="text-right font-medium">IC95</th><th className="text-right font-medium">p</th></tr></thead>
            <tbody>
              {[['EDGE · +1 yd/s', ef.edge_yd], ['IDL · +1 yd/s', ef.idl_yd], [`EDGE · +1 DE (${num(lab.sd_burst.EDGE)} yd/s)`, ef.edge_sd], [`IDL · +1 DE (${num(lab.sd_burst.IDL)} yd/s)`, ef.idl_sd], ['Interacción burst × IDL', ef.inter_yd], ['Peso EDGE · +10 lb', ef.peso_edge], ['Peso IDL · +10 lb', ef.peso_idl]].map(([l, r]: any) => (
                <tr key={l} className="border-t border-slate-100"><td className="py-1">{l}</td><td className="text-right font-semibold tabular-nums">{num(r.OR)}</td><td className="text-right tabular-nums text-slate-500">{num(r.lo)}–{num(r.hi)}</td><td className="text-right text-slate-500">{pval(r.p)}</td></tr>
              ))}
            </tbody>
          </table>
          <Note>
            Por yarda/segundo el OR de IDL parece mayor, pero los IDL tienen menos dispersión de burst. Medido en desviaciones estándar de su propio grupo, el efecto es prácticamente idéntico ({num(ef.edge_sd.OR)} vs {num(ef.idl_sd.OR)}).
            La interacción es marginal (p = {num(ef.inter_yd.p, 3)}) y no se sostiene en los análisis de robustez: no hay evidencia sólida de que la relación cambie entre grupos.
          </Note>
        </Card>
        <Card className="lg:col-span-2" title="5. Distribución de burst por posición" subtitle="Porcentaje de snaps de pass rush en cada rango de 0.25 yd/s (población del modelo)">
          <div className="h-60">
            <ResponsiveContainer>
              <LineChart data={lab.distribucion}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="x" type="number" domain={[0, 6.5]} tickFormatter={(v) => Number(v).toFixed(1)} fontSize={10} />
                <YAxis tickFormatter={(v) => `${Number(v).toFixed(0)}%`} fontSize={10} width={34} />
                <Tooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} labelFormatter={(v: any) => `${(Number(v) - 0.125).toFixed(2)}–${(Number(v) + 0.125).toFixed(2)} yd/s`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {Object.keys(POS_COLOR).map((p) => <Line key={p} dataKey={p} stroke={POS_COLOR[p]} dot={false} strokeWidth={2} />)}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left font-medium">Posición</th><th className="text-right font-medium">Snaps</th><th className="text-right font-medium">P10</th><th className="text-right font-medium">P25</th><th className="text-right font-medium">Mediana</th><th className="text-right font-medium">P75</th><th className="text-right font-medium">P90</th><th className="text-right font-medium">DE</th></tr></thead>
            <tbody>{lab.cuantiles_posicion.map((r: any) => <tr key={r.officialPosition} className="border-t border-slate-100"><td className="py-0.5 font-semibold" style={{ color: POS_COLOR[r.officialPosition] }}>{r.officialPosition}</td><td className="text-right">{int(r.count)}</td>{['p10', 'p25', 'p50', 'p75', 'p90', 'std'].map((k) => <td key={k} className="text-right tabular-nums">{num(r[k])}</td>)}</tr>)}</tbody>
          </table>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="6. Burst habitual vs tasa de presión por jugador" subtitle={`${disp.length} jugadores con ≥50 jugadas modelables · tamaño = oportunidades · clic para abrir el perfil`}>
          <div className="h-80">
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="burst_med" name="Burst mediano" domain={['auto', 'auto']} tickFormatter={(v) => Number(v).toFixed(1)} fontSize={10} label={{ value: 'burst mediano (yd/s)', position: 'insideBottom', offset: -8, fontSize: 10 }} />
                <YAxis type="number" dataKey="tasa" name="Tasa" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={36} />
                <ZAxis type="number" dataKey="snaps" range={[20, 160]} />
                <Tooltip content={({ active, payload }: any) => active && payload?.length ? (
                  <div className="rounded border border-slate-200 bg-white p-2 text-xs shadow"><div className="font-semibold">{payload[0].payload.nombre} <span className="text-slate-500">{payload[0].payload.pos} · {payload[0].payload.equipo}</span></div>
                    <div>Burst {num(payload[0].payload.burst_med)} yd/s · presión {pct(payload[0].payload.tasa)} · {payload[0].payload.snaps} snaps · O/E {num(payload[0].payload.o_e)}</div></div>) : null} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {['EDGE', 'IDL'].map((g) => <Scatter key={g} name={g} data={disp.filter((d: any) => d.grupo === g)} fill={grupoColor(g)} fillOpacity={0.6} onClick={(d: any) => onPlayer(d.nflId ?? d.payload?.nflId)} cursor="pointer" />)}
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-600">
            {['EDGE', 'IDL'].map((g) => { const c = lab.correlaciones[g]; return <span key={g} className="mr-3"><b style={{ color: grupoColor(g) }}>{g}</b>: Pearson r = {num(c.pearson)} ({pval(c.p_pearson)}), Spearman ρ = {num(c.spearman)}, n = {c.n}.</span> })}
          </p>
        </Card>

        <Card title="7. Explosividad habitual vs explosividad en cada jugada" subtitle="Modelo M4: separa el promedio del jugador (entre jugadores) de su variación jugada a jugada (dentro del jugador)">
          <Forest rows={ed} />
          <Note>
            Ambos componentes se asocian con más presión. Los jugadores más explosivos en promedio presionan más, y un mismo jugador presiona más en las jugadas en que sale más rápido de lo habitual.
            El componente «dentro del jugador» no puede atribuirse a diferencias de talento entre jugadores, aunque puede reflejar la respuesta del bloqueador o el diseño de la jugada.
          </Note>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="8. Burst vs getoff vs aceleración inicial" subtitle="Cada métrica sustituye al burst en el mismo modelo M3 · OR por +1 desviación estándar dentro del grupo">
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={alt.map((a: any) => ({ ...a, eE: [a.or_sd_EDGE - a.lo_EDGE, a.hi_EDGE - a.or_sd_EDGE], eI: [a.or_sd_IDL - a.lo_IDL, a.hi_IDL - a.or_sd_IDL] }))}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="nombre" fontSize={10} interval={0} />
                <YAxis domain={[0.9, 'auto']} fontSize={10} width={34} tickFormatter={(v) => Number(v).toFixed(2)} />
                <Tooltip formatter={(v: any) => num(Number(v), 3)} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="or_sd_EDGE" name="EDGE" fill={COLOR.EDGE}><ErrorBar dataKey="eE" width={4} stroke="#0f172a" /></Bar>
                <Bar dataKey="or_sd_IDL" name="IDL" fill={COLOR.IDL}><ErrorBar dataKey="eI" width={4} stroke="#0f172a" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left font-medium">Métrica</th><th className="text-right font-medium">AUC del modelo</th><th className="text-right font-medium">Corr. con burst</th><th className="text-right font-medium">Corr. con getoff</th></tr></thead>
            <tbody>{alt.map((a: any) => <tr key={a.metrica} className="border-t border-slate-100"><td className="py-0.5">{a.nombre}</td><td className="text-right tabular-nums">{num(a.auc, 3)}</td><td className="text-right tabular-nums">{num(lab.corr_metricas[a.metrica].burst)}</td><td className="text-right tabular-nums">{num(lab.corr_metricas[a.metrica].getoff)}</td></tr>)}</tbody>
          </table>
          <p className="mt-2 text-xs text-slate-600">El burst es la métrica con mayor asociación y mejor discriminación. Getoff está muy correlacionado con burst, por eso no se usan juntos. La aceleración máxima inicial aporta poco, en parte porque la columna «a» del tracking no tiene signo.</p>
        </Card>
        <Card title="9. Modelo M3 completo" subtitle={`Regresión logística · ${int(lab.ajuste.n)} rusher-jugadas de ${lab.ajuste.jugadores} jugadores · IC95 robustos agrupados por jugador`}>
          <Forest rows={forestMain} />
          <p className="mt-2 text-xs text-slate-600">OR &gt; 1 se asocia con más probabilidad de presión. Situaciones de 3.er down y play action tienen asociaciones del mismo orden que +1 yd/s de burst: el contexto pesa tanto como el físico.</p>
        </Card>
      </div>

      <Card title="10. Robustez del resultado" subtitle="El OR de burst se reestima cambiando la población; si el hallazgo dependiera de una decisión arbitraria, cambiaría mucho">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Análisis</th><th className="text-right">n</th><th className="text-right">Jugadores</th><th className="text-right">OR burst EDGE</th><th className="text-right">OR burst IDL</th><th className="text-right">OR peso (+10 lb)</th></tr></thead>
          <tbody>{lab.robustez.map((r: any) => (
            <tr key={r.analisis} className="border-b border-slate-100"><td className="py-1">{r.analisis}</td><td className="text-right">{int(r.n)}</td><td className="text-right">{r.jugadores}</td>
              <td className="text-right tabular-nums">{num(r.or_edge)} <span className="text-slate-400">[{num(r.lo_edge)}–{num(r.hi_edge)}]</span></td>
              <td className="text-right tabular-nums">{num(r.or_idl)} <span className="text-slate-400">[{num(r.lo_idl)}–{num(r.hi_idl)}]</span></td>
              <td className="text-right tabular-nums">{num(r.or_peso, 3)} <span className="text-slate-400">{pval(r.p_peso)}</span></td></tr>
          ))}</tbody>
        </table>
        <div className="mt-3"><Note tone="warn">El modelo discrimina de forma modesta (AUC {num(lab.ajuste.auc)}, R² de McFadden {num(lab.ajuste.mcfadden, 3)}): la mayor parte de lo que determina una presión en una jugada concreta no está en estas variables. Úsalo para comparar promedios y perfiles, no para predecir jugadas individuales.</Note></div>
      </Card>
    </div>
  )
}
