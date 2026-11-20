import { ReactNode, useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ErrorBar, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import PlayerSearch, { JugadorLista } from '../PlayerSearch'
import { Badge, Card, ErrorBox, Kpi, Loading, Note, PercentileBar, Select, COLOR, altura, grupoColor, int, num, pct } from '../ui'

const err = (r: any) => [r.tasa - r.ic_lo, r.ic_hi - r.tasa]
const BLOQUEO: Record<string, string> = { PP: 'Protección estándar', PA: 'Protección play action', PT: 'Post', SW: 'Cambio (switch)', CL: 'Segundo nivel', CH: 'Chip', PU: 'Recogida desde backfield', SR: 'Set & release', BH: 'Ayuda desde backfield', UP: 'Pull', PR: 'Pocket roll', NB: 'Sin bloqueo' }

export default function Enfrentamientos({ lista, equipos, onPlayer, inicial }: { lista: JugadorLista[]; equipos: string[]; onPlayer: (id: number) => void; inicial?: { b: number; d: number } | null }) {
  const [equipo, setEquipo] = useState('')
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [estrato, setEstrato] = useState('OT vs EDGE')
  const [par, setPar] = useState<{ b: number; d: number } | null>(inicial ?? null)
  useEffect(() => { setData(null); api('enfrentamientos', { equipo }).then((d) => { setData(d); setError(null) }).catch((e) => setError(e.message)) }, [equipo])
  useEffect(() => { if (inicial) setPar(inicial) }, [inicial])

  if (error) return <ErrorBox error={error} />
  return (
    <div className="space-y-4">
      <ParSelector lista={lista} par={par} setPar={setPar} onPlayer={onPlayer} />
      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <Select className="w-48" label="Equipo (como ofensiva o defensiva)" value={equipo} onChange={setEquipo} options={[{ value: '', label: 'Todos' }, ...equipos.map((t) => ({ value: t, label: t }))]} />
          <p className="text-xs text-slate-500">Un enfrentamiento es un bloqueador en una jugada con el defensor que PFF le asigna (<code>pff_nflIdBlockedPlayer</code>). «Perdido» = presión permitida o superado por el defensor.</p>
        </div>
      </Card>
      {!data ? <Loading /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Kpi label="Enfrentamientos" value={int(data.n)} sub="bloqueador vs pass rusher" />
            <Kpi label="Parejas distintas" value={int(data.parejas)} />
            <Kpi label="Bloqueadores" value={int(data.bloqueadores)} />
            <Kpi label="Defensores" value={int(data.defensores)} />
            <Kpi label="Bloqueos perdidos" value={pct(data.perdido)} sub={`presión permitida: ${pct(data.permitido)}`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Posición del bloqueador vs perfil del defensor" subtitle="% de bloqueos perdidos · IC95">
              <div className="h-56">
                <ResponsiveContainer>
                  <BarChart data={['T', 'G', 'C'].map((p) => {
                    const e = data.cruce.find((r: any) => r.officialPosition === p && r.def_grupo === 'EDGE')
                    const i = data.cruce.find((r: any) => r.officialPosition === p && r.def_grupo === 'IDL')
                    return { pos: p, EDGE: e?.tasa, IDL: i?.tasa, eE: e ? err(e) : [0, 0], eI: i ? err(i) : [0, 0], nE: e?.n, nI: i?.n }
                  })}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="pos" fontSize={11} tickFormatter={(v) => ({ T: 'Tackle', G: 'Guardia', C: 'Centro' } as any)[v]} />
                    <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                    <Tooltip formatter={(v: any, n: any, it: any) => [`${pct(Number(v))} (n=${n === 'EDGE' ? it.payload.nE : it.payload.nI})`, `vs ${n}`]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="EDGE" fill={COLOR.EDGE}><ErrorBar dataKey="eE" width={4} stroke="#0f172a" /></Bar>
                    <Bar dataKey="IDL" fill={COLOR.IDL}><ErrorBar dataKey="eI" width={4} stroke="#0f172a" /></Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-slate-600">Los tackles contra EDGE son el enfrentamiento más difícil para la ofensiva. Por eso las comparaciones físicas de abajo se hacen dentro de cada tipo de enfrentamiento.</p>
            </Card>

            <Card className="lg:col-span-2" title="Características físicas en el enfrentamiento" subtitle="Separado por tipo de enfrentamiento para no confundir el físico con la posición"
              right={<div className="flex rounded-md border border-slate-300 text-xs">{Object.keys(data.fisico).map((k) => <button key={k} onClick={() => setEstrato(k)} className={`px-2 py-1 ${estrato === k ? 'bg-slate-800 text-white' : 'text-slate-600'}`}>{k}</button>)}</div>}>
              {data.fisico[estrato] && (
                <div className="grid gap-3 md:grid-cols-3">
                  {[['burst_defensor', 'Burst del defensor en esa jugada (quintil)', (r: any) => `Q${r.q} (${num(r.lo, 1)}–${num(r.hi, 1)})`],
                    ['dif_peso', 'Peso del defensor − peso del bloqueador', (r: any) => r.rango],
                    ['dif_altura', 'Estatura del defensor − estatura del bloqueador', (r: any) => r.rango]].map(([k, t, lab]: any) => {
                    const rows = data.fisico[estrato][k].filter((r: any) => r.n >= 30).map((r: any) => ({ ...r, l: lab(r), e: err(r) }))
                    return (
                      <div key={k}>
                        <div className="mb-1 text-xs font-semibold text-slate-700">{t}</div>
                        <div className="h-48">
                          <ResponsiveContainer>
                            <BarChart data={rows}>
                              <CartesianGrid strokeDasharray="3 3" vertical={false} />
                              <XAxis dataKey="l" fontSize={9} interval={0} angle={-20} textAnchor="end" height={44} />
                              <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={32} domain={[0, 'auto']} />
                              <Tooltip formatter={(v: any, _n: any, it: any) => [`${pct(Number(v))} (n=${it.payload.n})`, 'Perdidos']} />
                              <Bar dataKey="tasa" fill={k === 'burst_defensor' ? '#1d4ed8' : '#64748b'}><ErrorBar dataKey="e" width={4} stroke="#0f172a" /></Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
              <Note>
                Dentro del mismo tipo de enfrentamiento, la explosividad del defensor en esa jugada separa más los resultados que las diferencias de peso o estatura. Se ocultan los rangos con menos de 30 casos.
                Son asociaciones: un defensor puede salir más rápido precisamente porque el bloqueador tardó en ponerse en posición.
              </Note>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Dobles equipos" subtitle="Tasa de presión del defensor según cuántos bloqueadores le asigna PFF">
              <div className="h-52">
                <ResponsiveContainer>
                  <BarChart data={['Sin bloqueador', 'Un bloqueador', 'Doble equipo'].map((b) => {
                    const e = data.dobles.find((r: any) => r.grupo === 'EDGE' && r.bloqueo === b)
                    const i = data.dobles.find((r: any) => r.grupo === 'IDL' && r.bloqueo === b)
                    return { b, EDGE: e?.tasa, IDL: i?.tasa, eE: e ? err(e) : [0, 0], eI: i ? err(i) : [0, 0], nE: e?.n, nI: i?.n }
                  })}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="b" fontSize={10} />
                    <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                    <Tooltip formatter={(v: any, n: any, it: any) => [`${pct(Number(v))} (n=${n === 'EDGE' ? it.payload.nE : it.payload.nI})`, n]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="EDGE" fill={COLOR.EDGE}><ErrorBar dataKey="eE" width={4} stroke="#0f172a" /></Bar>
                    <Bar dataKey="IDL" fill={COLOR.IDL}><ErrorBar dataKey="eI" width={4} stroke="#0f172a" /></Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-xs text-slate-600">Los defensores con doble equipo presionan menos, pero recibirlo también indica que la ofensiva los considera una amenaza. Por eso conviene leer la tasa de presión junto con el % de dobles.</p>
            </Card>
            <Card title="Defensores que más atraen dobles equipos" subtitle="% de sus snaps de rush con ≥2 bloqueadores asignados · ≥100 snaps">
              <table className="w-full text-xs">
                <tbody>{data.mas_doblados.map((r: any) => (
                  <tr key={r.nflId} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onPlayer(r.nflId)}>
                    <td className="py-1"><span className="font-medium">{r.nombre}</span> <span className="text-slate-400">{r.pos} · {r.equipo}</span></td>
                    <td className="text-right tabular-nums">{r.dobles}/{r.snaps}</td><td className="w-16 text-right font-semibold tabular-nums">{pct(r.pct_doble)}</td></tr>
                ))}</tbody>
              </table>
            </Card>
            <Card title="Tipos de bloqueo" subtitle="Bloqueos perdidos y presión permitida por tipo (≥20 casos)">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-slate-500"><th>Tipo</th><th className="text-right">n</th><th className="text-right">Perdidos</th><th className="text-right">Pres. perm.</th></tr></thead>
                <tbody>{data.tipos.map((r: any) => (
                  <tr key={r.pff_blockType} className="border-t border-slate-100"><td className="py-1"><b>{r.pff_blockType}</b> <span className="text-slate-500">{BLOQUEO[r.pff_blockType] ?? ''}</span></td>
                    <td className="text-right">{int(r.n)}</td><td className="text-right">{pct(r.tasa)}</td><td className="text-right">{pct(r.tasa_perm)}</td></tr>
                ))}</tbody>
              </table>
              <p className="mt-2 text-[11px] text-slate-500">El tipo de bloqueo depende de la asignación del plan: PP y SW enfrentan al rusher de forma directa y se pierden más.</p>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ParejasTabla title="Enfrentamientos más repetidos" rows={data.parejas_top} onPick={(b, d) => setPar({ b, d })} />
            <ParejasTabla title="Parejas con más bloqueos perdidos" subtitle="Mínimo 10 enfrentamientos; con muestras pequeñas el porcentaje es poco estable" rows={data.parejas_dominadas} onPick={(b, d) => setPar({ b, d })} />
          </div>
        </>
      )}
    </div>
  )
}

function ParejasTabla({ title, subtitle, rows, onPick }: { title: string; subtitle?: string; rows: any[]; onPick: (b: number, d: number) => void }) {
  return (
    <Card title={title} subtitle={subtitle ?? 'Clic para ver el historial del enfrentamiento'}>
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-white"><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Bloqueador</th><th>Defensor</th><th className="text-right">n</th><th className="text-right">Perdidos</th><th className="text-right">Pres. def.</th></tr></thead>
          <tbody>{rows.map((r: any) => (
            <tr key={`${r.nflId}-${r.defId}`} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => onPick(r.nflId, r.defId)}>
              <td className="py-1">{r.bloqueador} <span className="text-slate-400">{r.pos_b} · {r.equipo_b}</span></td>
              <td>{r.defensor} <span className="text-slate-400">{r.pos_d} · {r.equipo_d}</span></td>
              <td className="text-right tabular-nums">{r.n}</td><td className="text-right tabular-nums">{r.perdidos} <span className="text-slate-400">({pct(r.tasa, 0)})</span></td><td className="text-right tabular-nums">{r.pres_def}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </Card>
  )
}

function ParSelector({ lista, par, setPar, onPlayer }: { lista: JugadorLista[]; par: { b: number; d: number } | null; setPar: (p: { b: number; d: number } | null) => void; onPlayer: (id: number) => void }) {
  const [blk, setBlk] = useState<JugadorLista | null>(null)
  const [riv, setRiv] = useState<any>(null)
  const [det, setDet] = useState<any>(null)
  const [err_, setErr] = useState<string | null>(null)
  useEffect(() => { if (blk) api(`rivales/${blk.nflId}`).then(setRiv).catch(() => setRiv(null)) }, [blk])
  useEffect(() => {
    if (!par) return
    setDet(null)
    api('pareja', { bloqueador: par.b, defensor: par.d }).then((d) => { setDet(d); setErr(null) }).catch((e) => setErr(e.message))
  }, [par])

  return (
    <Card title="Comparador de enfrentamientos" subtitle="Elige un bloqueador o un defensor y luego a su rival para ver el historial jugada por jugada">
      <div className="grid gap-3 md:grid-cols-2">
        <PlayerSearch lista={lista} label="Jugador (bloqueador u ofensivo / pass rusher)" filtro={(p) => p.block >= 5 || p.rush >= 5} onPick={(p) => { setBlk(p); setRiv(null) }} placeholder="Ej. Daryl Williams, T.J. Watt…" />
        <div>
          <label className="text-xs font-medium text-slate-600">Rival {riv?.lado === 'bloqueador' ? '(defensores que enfrentó)' : riv?.lado === 'defensor' ? '(bloqueadores que lo enfrentaron)' : ''}</label>
          <select className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" disabled={!riv?.rivales?.length} value=""
            onChange={(e) => { const id = Number(e.target.value); if (!blk || !riv) return; setPar(riv.lado === 'bloqueador' ? { b: blk.nflId, d: id } : { b: id, d: blk.nflId }) }}>
            <option value="">{blk ? (riv?.rivales?.length ? `${riv.rivales.length} rivales — elige uno` : 'Sin enfrentamientos registrados') : 'Primero elige un jugador'}</option>
            {riv?.rivales?.map((r: any) => <option key={r.nflId} value={r.nflId}>{r.nombre} ({r.pos}, {r.equipo}) · {r.n} enfr. · {r.perdidos} perdidos</option>)}
          </select>
        </div>
      </div>
      {err_ && <div className="mt-3"><ErrorBox error={err_} /></div>}
      {par && !det && !err_ && <Loading />}
      {det && <ParDetalle d={det} onPlayer={onPlayer} onClose={() => { setPar(null); setDet(null) }} />}
    </Card>
  )
}

const FIS = [['burst', 'Burst', 'yd/s'], ['getoff', 'Getoff', 'yd'], ['s_max', 'Vel. máx.', 'yd/s'], ['a_max', 'Acel. máx.', 'yd/s²']]

function ParDetalle({ d, onPlayer, onClose }: { d: any; onPlayer: (id: number) => void; onClose: () => void }) {
  const r = d.resumen
  const lado = (p: any, rol: string, color: string, extra: ReactNode) => (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-start justify-between">
        <div><div className="text-[11px] font-semibold uppercase" style={{ color }}>{rol}</div>
          <button className="text-base font-bold text-slate-900 hover:underline" onClick={() => onPlayer(p.nflId)}>{p.nombre}</button>
          <div className="text-xs text-slate-500">{p.pos} · {p.equipos.join('/')} · {p.peso} lb · {altura(p.altura_in)}</div></div>
        <div className="text-right text-xs">{extra}</div>
      </div>
      <table className="mt-2 w-full text-xs"><tbody>{FIS.map(([k, l, u]) => p.fisico[k] && (
        <tr key={k}><td className="py-0.5 text-slate-600">{l} <span className="text-slate-400">{u}</span></td><td className="text-right tabular-nums">{num(p.fisico[k].valor)}</td><td className="pl-3"><PercentileBar value={p.fisico[k].percentil} /></td></tr>
      ))}</tbody></table>
    </div>
  )
  return (
    <div className="mt-4 space-y-3 border-t border-slate-200 pt-4">
      <div className="flex justify-end"><button className="text-xs text-slate-500 hover:text-rose-600" onClick={onClose}>Cerrar ×</button></div>
      <div className="grid gap-3 lg:grid-cols-3">
        {lado(d.bloqueador, 'Bloqueador', COLOR.OT, <><div>Efectividad general</div><div className="text-base font-bold">{pct(d.bloqueador.efectividad_total)}</div><div className="text-slate-400">{d.bloqueador.snaps_total} bloqueos</div></>)}
        <div className="rounded-lg border border-blue-200 bg-blue-50/40 p-3">
          <div className="text-[11px] font-semibold uppercase text-blue-700">En este enfrentamiento</div>
          <div className="mt-1 grid grid-cols-2 gap-2 text-center">
            <div><div className="text-2xl font-bold">{r.n}</div><div className="text-[11px] text-slate-500">enfrentamientos · {r.partidos} partido(s)</div></div>
            <div><div className="text-2xl font-bold text-blue-700">{pct(r.efectividad)}</div><div className="text-[11px] text-slate-500">efectividad del bloqueador</div></div>
            <div><div className="text-lg font-bold">{r.perdidos}</div><div className="text-[11px] text-slate-500">perdidos (IC95 {pct(r.ic_lo, 0)}–{pct(r.ic_hi, 0)})</div></div>
            <div><div className="text-lg font-bold">{r.permitidas}</div><div className="text-[11px] text-slate-500">presiones permitidas · {r.sacks} sacks</div></div>
          </div>
          <div className="mt-2 space-y-0.5 text-xs text-slate-600">
            <div>Diferencia de peso (defensor − bloqueador): <b>{r.dif_peso > 0 ? '+' : ''}{r.dif_peso} lb</b> · estatura {r.dif_altura > 0 ? '+' : ''}{r.dif_altura} in</div>
            <div>Burst mediano del defensor en estas jugadas: <b>{num(r.burst_def_med)} yd/s</b></div>
            <div>Con doble equipo: {r.dobles} jugadas{r.perdida_doble !== null && ` (${pct(r.perdida_doble)} perdidos vs ${pct(r.perdida_solo)} sin doble)`}</div>
            <div>Presiones totales del defensor en estas jugadas: {r.pres_def} (pueden haber sido sobre otro bloqueador)</div>
          </div>
          <div className="mt-2 flex flex-wrap gap-1">{d.tipos.map((t: any) => <Badge key={t.tipo}>{t.tipo}: {t.n} ({t.perdidos} perd.)</Badge>)}</div>
        </div>
        {lado(d.defensor, 'Defensor', COLOR.EDGE, <><div>Presión general</div><div className="text-base font-bold">{pct(d.defensor.tasa_total)}</div><div className="text-slate-400">{d.defensor.snaps_total} snaps · O/E {num(d.defensor.o_e)}</div></>)}
      </div>
      {r.n < 15 && <Note tone="warn">Solo {r.n} enfrentamientos: el resultado de esta pareja tiene mucha incertidumbre. Úsalo como guía para revisar video.</Note>}
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-white"><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Partido</th><th>Q · reloj</th><th>Down</th><th>Bloqueo</th><th>Burst def.</th><th>Resultado</th><th>Jugada</th></tr></thead>
          <tbody>{d.historial.map((h: any) => (
            <tr key={`${h.gameId}-${h.playId}`} className="border-b border-slate-100 align-top">
              <td className="whitespace-nowrap py-1">{h.partido}</td><td className="whitespace-nowrap">Q{h.quarter} · {h.gameClock}</td><td className="whitespace-nowrap">{h.down}.º y {h.yardsToGo}</td>
              <td>{h.pff_blockType ?? '—'}{h.doble && <span className="ml-1 text-[10px] text-amber-700">doble</span>}{h.pff_playAction ? <span className="ml-1 text-[10px] text-slate-500">PA</span> : null}</td>
              <td className="tabular-nums">{num(h.def_burst)}</td>
              <td><Badge color={h.lost ? 'red' : 'green'}>{h.resultado}</Badge></td>
              <td className="text-slate-500">{h.playDescription}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-500">Colores de grupo: <span style={{ color: grupoColor('EDGE') }}>EDGE</span>, <span style={{ color: grupoColor('IDL') }}>IDL</span>. «Superado sin presión» corresponde a <code>pff_beatenByDefender</code>.</p>
    </div>
  )
}
