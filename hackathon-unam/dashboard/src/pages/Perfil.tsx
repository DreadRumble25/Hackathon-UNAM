import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import PlayerSearch, { JugadorLista } from '../PlayerSearch'
import { Badge, Card, ErrorBox, Kpi, Loading, Note, PercentileBar, altura, grupoColor, histogram, int, num, pct, pval } from '../ui'

export default function Perfil({ nflId, lista, onSelect, onCompare }: { nflId: number | null; lista: JugadorLista[]; onSelect: (id: number) => void; onCompare: (id: number) => void }) {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!nflId) return
    setData(null)
    api(`jugador/${nflId}`).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message))
  }, [nflId])

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full max-w-md"><PlayerSearch lista={lista} onPick={(p) => onSelect(p.nflId)} label="Buscar jugador (nombre, equipo o posición)" placeholder="Ej. Garrett, Donald, KC, DT…" /></div>
          {data && <button className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100" onClick={() => onCompare(data.info.nflId)}>Comparar con otros jugadores →</button>}
          {!nflId && <p className="text-sm text-slate-500">Selecciona un jugador, o haz clic en un nombre en cualquier módulo.</p>}
        </div>
      </Card>

      {error && <ErrorBox error={error} />}
      {nflId && !data && !error && <Loading />}
      {data && (
        <>
          <Header d={data} />
          <Fisico d={data} />
          {data.rush && <Rush d={data} />}
          {data.block && <Block d={data} onSelect={onSelect} />}
          {!data.rush && !data.block && <Note>Este jugador no tiene snaps de pass rush ni de pass block: solo se muestran sus métricas físicas.</Note>}
        </>
      )}
    </div>
  )
}

function Header({ d }: { d: any }) {
  const i = d.info
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-slate-900">{i.nombre}</h2>
            <Badge color="blue">{i.posicion}</Badge>
            {i.grupo !== 'OTRO' && <span className="rounded-full px-2 py-0.5 text-[11px] font-semibold text-white" style={{ background: grupoColor(i.grupo) }}>{i.grupo}</span>}
          </div>
          <p className="mt-1 text-sm text-slate-600">Equipo en el periodo (semanas 1–8, 2021): <b>{i.equipos.join(', ')}</b>{i.universidad ? ` · ${i.universidad}` : ''}</p>
          <p className="mt-1 text-xs text-slate-500">Alineación más frecuente: {i.alineaciones.map((a: any) => `${a.pos} (${pct(a.pct, 0)})`).join(' · ')}</p>
        </div>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div><div className="text-[11px] uppercase text-slate-500">Peso</div><div className="text-lg font-bold">{i.peso} lb</div><div className="text-[11px] text-slate-400">{(i.peso * 0.4536).toFixed(0)} kg</div></div>
          <div><div className="text-[11px] uppercase text-slate-500">Estatura</div><div className="text-lg font-bold">{i.altura}</div><div className="text-[11px] text-slate-400">{altura(i.altura_in)}</div></div>
          <div><div className="text-[11px] uppercase text-slate-500">Snaps</div><div className="text-lg font-bold">{int(Object.values(i.roles as Record<string, number>).reduce((a, b) => a + b, 0))}</div>
            <div className="text-[11px] text-slate-400">{Object.entries(i.roles).map(([k, v]) => `${k}: ${v}`).join(' · ')}</div></div>
        </div>
      </div>
    </Card>
  )
}

function Fisico({ d }: { d: any }) {
  const f = d.fisico
  const hist = useMemo(() => histogram(f.distribucion_burst.valores, 14), [f])
  const bin = f.distribucion_burst.jugador !== null ? hist.find((b) => f.distribucion_burst.jugador >= b.x0 && f.distribucion_burst.jugador <= b.x1) : null
  if (!f.metricas.length) return <Note>Sin datos de tracking para este jugador.</Note>
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2" title="Características físicas y de movimiento" subtitle={`Mediana por jugada en sus ${f.jugadas} snaps de «${f.rol}» · comparación con ${f.pares} ${d.info.posicion} con ≥20 snaps en el mismo rol`}>
        <table className="w-full text-xs">
          <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1.5">Métrica</th><th className="text-right">Jugador</th><th className="text-right">Media pos.</th><th className="text-right">Mediana pos.</th><th className="pl-4">Percentil en su posición</th></tr></thead>
          <tbody>
            {f.metricas.map((m: any) => (
              <tr key={m.clave} className="border-b border-slate-100" title={m.descripcion}>
                <td className="py-1.5"><span className="font-medium text-slate-800">{m.etiqueta}</span> <span className="text-slate-400">{m.unidad}</span></td>
                <td className="text-right font-semibold tabular-nums">{num(m.valor)}</td>
                <td className="text-right tabular-nums text-slate-600">{num(m.media_pos)}</td>
                <td className="text-right tabular-nums text-slate-600">{num(m.mediana_pos)}</td>
                <td className="pl-4"><PercentileBar value={m.percentil} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] text-slate-500">Velocidad, aceleración y distancia se miden entre el snap y el pase, sack o scramble, así que dependen de cuánto dura cada jugada. Burst, getoff y aceleración inicial usan solo el primer segundo. La columna «a» del tracking no tiene signo: la aceleración incluye los frenados.</p>
      </Card>
      <Card title="Distribución de burst en su posición" subtitle={`${f.pares} ${d.info.posicion} · el jugador en rojo`}>
        <div className="h-56">
          <ResponsiveContainer>
            <BarChart data={hist}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="mid" tickFormatter={(v) => Number(v).toFixed(1)} fontSize={10} />
              <YAxis allowDecimals={false} fontSize={10} width={28} />
              <Tooltip formatter={(v: any) => [`${v} jugadores`, 'Frecuencia']} labelFormatter={(v: any) => `${Number(v).toFixed(2)} yd/s`} />
              <Bar dataKey="n">{hist.map((b) => <Cell key={b.mid} fill={b === bin ? '#dc2626' : '#94a3b8'} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-xs text-slate-600">Burst del jugador: <b>{num(f.distribucion_burst.jugador)} yd/s</b>. Una característica física por sí sola no determina la calidad del jugador.</p>
      </Card>
    </div>
  )
}

function Rush({ d }: { d: any }) {
  const r = d.rush
  const hist = useMemo(() => histogram(r.distribucion_tasa, 14, 0), [r])
  const bin = hist.find((b) => r.tasa >= b.x0 && r.tasa <= b.x1)
  const comp = [
    { k: 'Observada', v: r.tasa, err: [r.tasa - r.ic_lo, r.ic_hi - r.tasa], c: '#1e40af' },
    { k: 'Esperada (modelo)', v: r.tasa_esp, c: '#64748b' },
    { k: 'Ajustada por muestra', v: r.tasa_ajustada, c: '#0d9488' },
    { k: `Media ${r.pos}`, v: r.media_pos_tasa, c: '#cbd5e1' },
  ].filter((x) => x.v !== null && x.v !== undefined)
  const sit = r.situaciones.map((s: any) => ({ ...s, err: s.tasa !== null ? [s.tasa - s.ic_lo, s.ic_hi - s.tasa] : [0, 0] }))
  const sem = r.por_semana.map((w: any) => ({ ...w, esperada: w.snaps ? w.esperadas / w.snaps : null }))
  const sig = r.p_aj !== null && r.p_aj < 0.05
  const g = r.ganancia_burst
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
        <Kpi label="Oportunidades" value={int(r.snaps)} sub="snaps de pass rush" />
        <Kpi label="Hurries" value={int(r.hurries)} />
        <Kpi label="Hits" value={int(r.hits)} />
        <Kpi label="Sacks" value={int(r.sacks)} sub="incluye medios sacks" />
        <Kpi label="Presiones" value={int(r.presiones)} sub="hurry, hit o sack" />
        <Kpi label="Tasa observada" value={pct(r.tasa)} sub={`IC95 ${pct(r.ic_lo)}–${pct(r.ic_hi)}`} tone="blue" />
        <Kpi label="Tasa esperada" value={pct(r.tasa_esp)} sub={`en ${int(r.n_model)} jugadas modelables`} />
        <Kpi label="Observada / esperada" value={num(r.o_e)} sub={r.o_e !== null ? `${pval(r.p_aj)}${sig ? ' · significativo' : ' · no concluyente'}` : 'fuera del modelo'} tone={sig ? (r.o_e > 1 ? 'green' : 'red') : 'slate'} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Observada vs esperada vs ajustada" subtitle={`Tasa ajustada = shrinkage hacia la media de su grupo · percentil ${num(r.pct_tasa, 0)} entre ${r.pares} ${r.pos} con ≥50 snaps`}>
          <div className="h-56">
            <ResponsiveContainer>
              <BarChart data={comp}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="k" fontSize={10} interval={0} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                <Tooltip formatter={(v: any) => pct(Number(v))} />
                <Bar dataKey="v" name="Tasa">{comp.map((c) => <Cell key={c.k} fill={c.c} />)}<ErrorBar dataKey="err" width={6} stroke="#0f172a" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-500">La esperada usa su burst en cada jugada, su peso, su grupo y el contexto (down, distancia, play action, formación, rushers, alineación). La significancia corrige la sobredispersión entre jugadores.</p>
        </Card>
        <Card title="Rendimiento por situación" subtitle={`Barras: tasa del jugador con IC95 · línea: promedio de los ${r.grupo}`}>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={sit} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} domain={[0, 'auto']} />
                <YAxis type="category" dataKey="situacion" width={128} fontSize={10} interval={0} />
                <Tooltip formatter={(v: any, n: any, it: any) => (n === 'tasa' ? [`${pct(Number(v))} (${it.payload.presiones}/${it.payload.n}) · grupo ${pct(it.payload.ref_grupo)}`, 'Tasa'] : v)} />
                <Bar dataKey="tasa" fill="#2563eb"><ErrorBar dataKey="err" width={4} stroke="#0f172a" direction="x" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-500">Con pocas oportunidades en una situación, el intervalo es amplio: compara solo cuando no se traslapan.</p>
        </Card>
        <Card title="Distribución de la tasa de presión" subtitle={`${r.pares} ${r.pos} con ≥50 snaps · el jugador en rojo`}>
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={hist}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="mid" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} />
                <YAxis allowDecimals={false} fontSize={10} width={28} />
                <Tooltip formatter={(v: any) => [`${v} jugadores`, 'Frecuencia']} labelFormatter={(v: any) => pct(Number(v))} />
                <Bar dataKey="n">{hist.map((b) => <Cell key={b.mid} fill={b === bin ? '#dc2626' : '#94a3b8'} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-600">Media {r.pos}: {pct(r.media_pos_tasa)} · mediana {pct(r.mediana_pos_tasa)}</p>
          {g && (
            <Note>
              Burst mediano {num(r.burst_med)} yd/s vs mediana de los {r.pos} {num(g.mediana_pos)} yd/s ({g.delta >= 0 ? '+' : ''}{num(g.delta)}).
              Con el burst de cada jugada desplazado a la mediana, el modelo estimaría <b>{pct(g.p_mediana)}</b> vs {pct(g.p_actual)} actual. Es una asociación estadística, no una ganancia garantizada.
            </Note>
          )}
        </Card>
      </div>
      {sem.length > 1 && (
        <Card title="Evolución por semana" subtitle="Tasa observada vs esperada por el modelo en cada semana; con pocas jugadas por semana la variación es grande">
          <div className="h-52">
            <ResponsiveContainer>
              <LineChart data={sem}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week" tickFormatter={(v) => `S${v}`} fontSize={11} />
                <YAxis yAxisId="t" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                <YAxis yAxisId="b" orientation="right" fontSize={10} width={30} domain={['auto', 'auto']} />
                <Tooltip formatter={(v: any, n: any) => (n === 'Burst mediano' ? num(Number(v)) : pct(Number(v)))} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line yAxisId="t" dataKey="tasa" name="Observada" stroke="#1e40af" strokeWidth={2} />
                <Line yAxisId="t" dataKey="esperada" name="Esperada" stroke="#64748b" strokeDasharray="4 4" />
                <Line yAxisId="b" dataKey="burst" name="Burst mediano" stroke="#ea580c" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}
    </>
  )
}

function Block({ d, onSelect }: { d: any; onSelect: (id: number) => void }) {
  const b = d.block
  const vg = b.vs_grupo.map((x: any) => ({ ...x, err: [x.tasa_perdida - x.ic_lo, x.ic_hi - x.tasa_perdida] }))
  const hist = useMemo(() => histogram(b.distribucion_efectividad, 14), [b])
  const bin = hist.find((h) => b.efectividad >= h.x0 && b.efectividad <= h.x1)
  return (
    <>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Kpi label="Oportunidades" value={int(b.snaps)} sub="snaps de pass block" />
        <Kpi label="Presiones permitidas" value={int(b.permitidas)} sub={`${pct(b.tasa_permitida)} · ${int(b.sacks_perm)} sacks`} />
        <Kpi label="Superado sin presión" value={int(b.superado)} sub="beaten by defender" />
        <Kpi label="Bloqueos perdidos" value={int(b.perdidos)} sub="permitida o superado" />
        <Kpi label="Efectividad" value={pct(b.efectividad)} sub={`IC95 ${pct(b.ic_lo)}–${pct(b.ic_hi)}`} tone="blue" />
        <Kpi label="Efectividad ajustada" value={pct(b.efectividad_ajustada)} sub={`percentil ${num(b.pct_efectividad, 0)} entre ${b.pares} ${b.pos}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Contra qué perfil defensivo pierde más" subtitle="Bloqueos perdidos por grupo del defensor asignado · línea = promedio de su posición">
          <div className="h-48">
            <ResponsiveContainer>
              <BarChart data={vg}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="def_grupo" fontSize={11} />
                <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                <Tooltip formatter={(v: any, _n: any, it: any) => [`${pct(Number(v))} (${it.payload.perdidos}/${it.payload.n}) · su posición ${pct(it.payload.ref_pos)}`, 'Perdidos']} />
                <Bar dataKey="tasa_perdida">{vg.map((x: any) => <Cell key={x.def_grupo} fill={grupoColor(x.def_grupo)} />)}<ErrorBar dataKey="err" width={6} stroke="#0f172a" /></Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="mt-2 w-full text-xs">
            <thead><tr className="text-left text-slate-500"><th>Posición rival</th><th className="text-right">n</th><th className="text-right">Perdidos</th><th className="text-right">Ref. posición</th></tr></thead>
            <tbody>{b.vs_posicion.slice(0, 6).map((x: any) => <tr key={x.def_pos} className="border-t border-slate-100"><td>{x.def_pos}</td><td className="text-right">{x.n}</td><td className="text-right">{pct(x.tasa_perdida)}</td><td className="text-right text-slate-500">{pct(x.ref_pos)}</td></tr>)}</tbody>
          </table>
        </Card>
        <Card title="Tipos de bloqueo" subtitle="PP protección estándar · PA play action · PT post · SW cambio · CL segundo nivel · CH chip">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Tipo</th><th className="text-right">n</th><th className="text-right">% perdidos</th><th className="text-right">Ref. posición</th></tr></thead>
            <tbody>{b.tipos_bloqueo.map((t: any) => (
              <tr key={t.tipo} className="border-b border-slate-100"><td className="py-1 font-medium">{t.tipo}</td><td className="text-right">{t.n}</td>
                <td className={`text-right ${t.ref_pos !== null && t.n >= 20 && t.tasa_perdida > t.ref_pos * 1.5 ? 'font-semibold text-rose-700' : ''}`}>{pct(t.tasa_perdida)}</td>
                <td className="text-right text-slate-500">{pct(t.ref_pos)}</td></tr>
            ))}</tbody>
          </table>
          <p className="mt-2 text-[11px] text-slate-500">El tipo de bloqueo refleja la asignación del plan, no solo la calidad del bloqueador. En rojo: ≥20 casos y 50% por encima de su posición.</p>
          <div className="mt-3 text-xs font-semibold text-slate-700">Diferencia de peso con el defensor</div>
          <table className="w-full text-xs">
            <tbody>{b.vs_peso.map((x: any) => <tr key={x.rango} className="border-t border-slate-100"><td className="py-0.5">{x.rango}</td><td className="text-right">{x.n}</td><td className="text-right">{pct(x.tasa_perdida)}</td></tr>)}</tbody>
          </table>
        </Card>
        <Card title="Rivales más frecuentes" subtitle="Defensores asignados por PFF; haz clic para abrir su perfil">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Defensor</th><th className="text-right">Enfr.</th><th className="text-right">Perdidos</th><th className="text-right">Pres. perm.</th></tr></thead>
            <tbody>{b.rivales.map((x: any) => (
              <tr key={x.defId} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onSelect(x.defId)}>
                <td className="py-1">{x.def_name} <span className="text-slate-400">{x.def_pos}</span></td><td className="text-right">{x.n}</td><td className="text-right">{x.perdidos}</td><td className="text-right">{x.permitidas}</td></tr>
            ))}</tbody>
          </table>
          <div className="mt-3 h-32">
            <ResponsiveContainer>
              <BarChart data={hist}>
                <XAxis dataKey="mid" tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={9} />
                <YAxis hide allowDecimals={false} />
                <Tooltip formatter={(v: any) => [`${v} jugadores`, 'Frecuencia']} labelFormatter={(v: any) => pct(Number(v))} />
                <Bar dataKey="n">{hist.map((h) => <Cell key={h.mid} fill={h === bin ? '#dc2626' : '#94a3b8'} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] text-slate-500">Efectividad de {b.pares} {b.pos} con ≥50 bloqueos (media {pct(b.media_pos)}, mediana {pct(b.mediana_pos)}).</p>
        </Card>
      </div>
    </>
  )
}
