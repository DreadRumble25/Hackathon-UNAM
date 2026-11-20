import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import PlayerSearch, { JugadorLista } from '../PlayerSearch'
import { Card, Loading, Note, altura, int, num, pct, pval } from '../ui'

const COLORES = ['#dc2626', '#2563eb', '#0d9488', '#7c3aed']
const EQUIV: Record<string, string> = { DE: 'EDGE', OLB: 'EDGE', DT: 'IDL', NT: 'IDL', T: 'OT', G: 'IOL', C: 'IOL' }

export default function Comparador({ lista, ids, setIds, onPlayer }: { lista: JugadorLista[]; ids: number[]; setIds: (f: (v: number[]) => number[]) => void; onPlayer: (id: number) => void }) {
  const [datos, setDatos] = useState<Record<number, any>>({})
  useEffect(() => { for (const id of ids) if (!datos[id]) api(`jugador/${id}`).then((d) => setDatos((c) => ({ ...c, [id]: d }))).catch(() => undefined) }, [ids, datos])
  const todos = ids.map((id) => datos[id]).filter(Boolean)
  const grupos = new Set(todos.map((d) => EQUIV[d.info.posicion] ?? d.info.posicion))
  const base = todos[0]
  const filtroEq = (p: JugadorLista) => !base || (EQUIV[p.officialPosition] ?? p.officialPosition) === (EQUIV[base.info.posicion] ?? base.info.posicion)
  const [soloEq, setSoloEq] = useState(true)

  return (
    <div className="space-y-4">
      <Card title="Comparador de jugadores" subtitle="Hasta 4 jugadores. Por defecto solo se ofrecen posiciones equivalentes (EDGE: DE/OLB · IDL: DT/NT · OT: T · IOL: G/C)">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full max-w-md"><PlayerSearch lista={lista} filtro={soloEq ? filtroEq : undefined} onPick={(p) => setIds((v) => (v.includes(p.nflId) || v.length >= 4 ? v : [...v, p.nflId]))} label="Agregar jugador" /></div>
          <label className="flex items-center gap-1 text-xs text-slate-600"><input type="checkbox" checked={soloEq} onChange={(e) => setSoloEq(e.target.checked)} /> Solo posiciones equivalentes</label>
          {ids.length > 0 && <button className="text-xs text-slate-500 hover:text-rose-600" onClick={() => setIds(() => [])}>Limpiar</button>}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {ids.map((id, i) => (
            <span key={id} className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: COLORES[i], color: COLORES[i] }}>
              <button onClick={() => onPlayer(id)} className="hover:underline">{datos[id]?.info.nombre ?? '…'}</button>
              <button className="text-slate-400 hover:text-rose-600" onClick={() => setIds((v) => v.filter((x) => x !== id))}>×</button>
            </span>
          ))}
        </div>
      </Card>
      {ids.length > todos.length && <Loading />}
      {todos.length < 2 ? <Note>Agrega al menos dos jugadores para comparar. También puedes usar «Comparar» desde el perfil de un jugador.</Note> : (
        <>
          {grupos.size > 1 && <Note tone="warn">Estás comparando posiciones no equivalentes ({[...grupos].join(', ')}). Los percentiles se calculan dentro de la posición de cada jugador, así que indican posición relativa y no igualdad de valores absolutos.</Note>}
          <Tabla todos={todos} />
          <Graficas todos={todos} />
        </>
      )}
    </div>
  )
}

function met(d: any, k: string) { return d.fisico.metricas.find((m: any) => m.clave === k) }

function Tabla({ todos }: { todos: any[] }) {
  const filas: { l: string; v: (d: any) => string; p?: (d: any) => number | null; sec?: string }[] = [
    { sec: 'General', l: 'Posición · equipo', v: (d) => `${d.info.posicion} · ${d.info.equipos.join('/')}` },
    { l: 'Peso', v: (d) => `${d.info.peso} lb` },
    { l: 'Estatura', v: (d) => altura(d.info.altura_in) },
    { l: 'Alineación más frecuente', v: (d) => d.info.alineaciones[0] ? `${d.info.alineaciones[0].pos} (${pct(d.info.alineaciones[0].pct, 0)})` : '—' },
    ...['burst', 'getoff', 'a_max_1s', 's_max', 's_mean', 'a_max', 'dist'].map((k, i) => ({
      sec: i === 0 ? 'Físico y movimiento (mediana por jugada · percentil en su posición)' : undefined,
      l: '', k, v: (d: any) => { const m = met(d, k); return m ? `${num(m.valor)} ${m.unidad}` : '—' }, p: (d: any) => met(d, k)?.percentil ?? null,
    })) as any,
    { sec: 'Pass rush', l: 'Oportunidades', v: (d) => (d.rush ? int(d.rush.snaps) : '—') },
    { l: 'Presiones (hurry · hit · sack)', v: (d) => (d.rush ? `${d.rush.presiones} (${d.rush.hurries} · ${d.rush.hits} · ${d.rush.sacks})` : '—') },
    { l: 'Tasa observada [IC95]', v: (d) => (d.rush ? `${pct(d.rush.tasa)} [${pct(d.rush.ic_lo, 0)}–${pct(d.rush.ic_hi, 0)}]` : '—'), p: (d) => d.rush?.pct_tasa ?? null },
    { l: 'Tasa esperada', v: (d) => (d.rush ? pct(d.rush.tasa_esp) : '—') },
    { l: 'Tasa ajustada por muestra', v: (d) => (d.rush ? pct(d.rush.tasa_ajustada) : '—') },
    { l: 'Observada / esperada', v: (d) => (d.rush?.o_e != null ? `${num(d.rush.o_e)} (${pval(d.rush.p_aj)})` : '—'), p: (d) => d.rush?.pct_oe ?? null },
    { sec: 'Pass block', l: 'Oportunidades', v: (d) => (d.block ? int(d.block.snaps) : '—') },
    { l: 'Presiones permitidas', v: (d) => (d.block ? `${d.block.permitidas} (${d.block.sacks_perm} sacks)` : '—') },
    { l: 'Efectividad [IC95]', v: (d) => (d.block ? `${pct(d.block.efectividad)} [${pct(d.block.ic_lo, 0)}–${pct(d.block.ic_hi, 0)}]` : '—'), p: (d) => d.block?.pct_efectividad ?? null },
    { l: 'Efectividad ajustada', v: (d) => (d.block ? pct(d.block.efectividad_ajustada) : '—') },
  ]
  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-slate-200"><th className="py-1.5 text-left text-slate-500">Métrica</th>{todos.map((d, i) => <th key={d.info.nflId} className="py-1.5 text-right" style={{ color: COLORES[i] }}>{d.info.nombre}</th>)}</tr></thead>
          <tbody>{filas.flatMap((f: any, j) => {
            const rows = []
            if (f.sec) rows.push(<tr key={`s${j}`}><td colSpan={todos.length + 1} className="pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{f.sec}</td></tr>)
            const label = f.l || met(todos[0], f.k)?.etiqueta || f.k
            rows.push(
              <tr key={j} className="border-b border-slate-100"><td className="py-1 text-slate-600">{label}</td>
                {todos.map((d) => { const p = f.p ? f.p(d) : null; return <td key={d.info.nflId} className="py-1 text-right tabular-nums">{f.v(d)}{p !== null && p !== undefined && <span className={`ml-1 rounded px-1 text-[10px] ${p >= 75 ? 'bg-emerald-100 text-emerald-800' : p <= 25 ? 'bg-rose-100 text-rose-800' : 'bg-slate-100 text-slate-600'}`}>p{Number(p).toFixed(0)}</span>}</td> })}
              </tr>)
            return rows
          })}</tbody>
        </table>
      </div>
    </Card>
  )
}

function Graficas({ todos }: { todos: any[] }) {
  const keys = ['burst', 'getoff', 'a_max_1s', 's_max', 's_mean', 'a_max', 'dist']
  const perc = [
    ...keys.map((k) => ({ metrica: met(todos[0], k)?.etiqueta ?? k, ...Object.fromEntries(todos.map((d) => [d.info.nombre, met(d, k)?.percentil ?? null])) })),
    { metrica: 'Tasa de presión', ...Object.fromEntries(todos.map((d) => [d.info.nombre, d.rush?.pct_tasa ?? null])) },
    { metrica: 'Observada / esperada', ...Object.fromEntries(todos.map((d) => [d.info.nombre, d.rush?.pct_oe ?? null])) },
    { metrica: 'Efectividad de bloqueo', ...Object.fromEntries(todos.map((d) => [d.info.nombre, d.block?.pct_efectividad ?? null])) },
  ].filter((r: any) => todos.some((d) => r[d.info.nombre] !== null && r[d.info.nombre] !== undefined))
  const brutos = ['burst', 'getoff', 's_max'].map((k) => ({
    metrica: `${met(todos[0], k)?.etiqueta ?? k}`,
    ...Object.fromEntries(todos.map((d) => [d.info.nombre, met(d, k)?.valor ?? null])),
    media: met(todos[0], k)?.media_pos,
  }))
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Percentil dentro de su posición" subtitle="50 = mediana de su posición">
        <div className="h-96">
          <ResponsiveContainer>
            <BarChart data={perc} layout="vertical" margin={{ left: 30 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" domain={[0, 100]} fontSize={10} />
              <YAxis type="category" dataKey="metrica" width={150} fontSize={10} interval={0} />
              <Tooltip formatter={(v: any) => `percentil ${Number(v).toFixed(0)}`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <ReferenceLine x={50} stroke="#94a3b8" strokeDasharray="4 4" />
              {todos.map((d, i) => <Bar key={d.info.nflId} dataKey={d.info.nombre} fill={COLORES[i]} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Explosividad y velocidad en valores reales" subtitle={`Mediana por jugada · línea = media de los ${todos[0].info.posicion}`}>
        <div className="h-96">
          <ResponsiveContainer>
            <BarChart data={brutos}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="metrica" fontSize={10} interval={0} />
              <YAxis fontSize={10} width={30} />
              <Tooltip formatter={(v: any) => num(Number(v))} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {todos.map((d, i) => <Bar key={d.info.nflId} dataKey={d.info.nombre} fill={COLORES[i]} />)}
              <Bar dataKey="media" name={`Media ${todos[0].info.posicion}`} fill="#cbd5e1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-[11px] text-slate-500">Velocidad máxima y distancia dependen de la duración de cada jugada; burst y getoff solo usan el primer segundo y son más comparables.</p>
      </Card>
    </div>
  )
}
