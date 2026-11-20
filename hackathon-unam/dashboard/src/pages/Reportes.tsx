import { useEffect, useState } from 'react'
import { api } from '../api'
import { Badge, Card, ErrorBox, Loading, Note, Select, num, pct, pval } from '../ui'

const NOTA: Record<string, { color: 'green' | 'red' | 'blue' | 'slate'; label: string }> = {
  fortaleza: { color: 'green', label: 'Fortaleza' }, evaluar: { color: 'red', label: 'Evaluar' }, fisico: { color: 'blue', label: 'Físico' },
}

export default function Reportes({ equipos, onPlayer, inicial }: { equipos: string[]; onPlayer: (id: number) => void; inicial?: string }) {
  const [equipo, setEquipo] = useState(inicial || equipos[0] || '')
  const [min, setMin] = useState('50')
  const [r, setR] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { if (inicial) setEquipo(inicial) }, [inicial])
  useEffect(() => { if (!equipo && equipos.length) setEquipo(equipos[0]) }, [equipos, equipo])
  useEffect(() => {
    if (!equipo) return
    setR(null)
    api(`reporte/${equipo}`, { min_snaps: min }).then((d) => { setR(d); setError(null) }).catch((e) => setError(e.message))
  }, [equipo, min])

  const fmt = (m: any, v: number) => (m.formato === 'pct' ? pct(v) : num(v))
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-end gap-3 print:hidden">
          <Select className="w-40" label="Equipo" value={equipo} onChange={setEquipo} options={equipos.map((t) => ({ value: t, label: t }))} />
          <Select className="w-44" label="Mínimo de oportunidades" value={min} onChange={setMin} options={['20', '50', '100'].map((v) => ({ value: v, label: `≥ ${v} snaps` }))} />
          <button className="rounded-md bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700" onClick={() => window.print()}>Imprimir / guardar PDF</button>
          <p className="text-xs text-slate-500">Las notas se generan con reglas fijas sobre los datos (percentiles, O/E con p-valor, comparación con su posición). Son puntos de partida para revisar video, no conclusiones.</p>
        </div>
      </Card>
      {error && <ErrorBox error={error} />}
      {!r && !error && <Loading />}
      {r && (
        <>
          <section className="rounded-xl border border-slate-300 bg-white p-5 shadow-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-xl font-bold text-slate-900">Reporte de rendimiento · {r.equipo}</h2>
              <span className="text-xs text-slate-500">Temporada 2021, semanas 1–8 · {r.partidos} partidos · jugadas de pase · jugadores con ≥ {r.min_snaps} oportunidades</span>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-5">
              {r.metricas.map((m: any) => (
                <div key={m.clave} className={`rounded-lg border p-3 ${m.nivel === 'fortaleza' ? 'border-emerald-300 bg-emerald-50' : m.nivel === 'area' ? 'border-rose-300 bg-rose-50' : 'border-slate-200'}`}>
                  <div className="text-[11px] font-medium text-slate-600">{m.etiqueta}</div>
                  <div className="text-xl font-bold">{fmt(m, m.valor)}</div>
                  <div className="text-[11px] text-slate-500">lugar {m.rango ?? '—'} de {m.de} · liga {fmt(m, m.liga)}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold text-emerald-800">Fortalezas del equipo (top 8 de la liga)</h3>
                <ul className="mt-1 list-inside list-disc text-sm text-slate-700">{r.fortalezas.length ? r.fortalezas.map((m: any) => <li key={m.clave}>{m.etiqueta}: {fmt(m, m.valor)} (lugar {m.rango})</li>) : <li className="list-none text-slate-500">Ninguna métrica entre los 8 mejores.</li>}</ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-rose-800">Áreas a evaluar (últimos 8 de la liga)</h3>
                <ul className="mt-1 list-inside list-disc text-sm text-slate-700">{r.areas.length ? r.areas.map((m: any) => <li key={m.clave}>{m.etiqueta}: {fmt(m, m.valor)} (lugar {m.rango})</li>) : <li className="list-none text-slate-500">Ninguna métrica entre los 8 últimos.</li>}</ul>
              </div>
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Situaciones titulo="Defensa: presión generada por situación" sub="Tasa por snap de pass rush · liga = todos los equipos" rows={r.situaciones_defensa} mejor="alto" />
            <Situaciones titulo="Ofensiva: dropbacks con presión permitida" sub="% de dropbacks con al menos una presión · menor es mejor" rows={r.situaciones_ofensiva} mejor="bajo" />
          </div>

          <Card title={`Pass rushers (${r.rushers.length})`} subtitle="Ordenados por tasa ajustada por tamaño de muestra · percentiles frente a jugadores de su misma posición en la liga">
            <Jugadores rows={r.rushers} onPlayer={onPlayer} cols={[
              ['Snaps', (x) => x.snaps], ['Pres.', (x) => `${x.presiones} (${x.sacks} sk)`], ['Observada [IC95]', (x) => `${pct(x.tasa)} [${pct(x.ic_lo, 0)}–${pct(x.ic_hi, 0)}]`],
              ['Esperada', (x) => pct(x.tasa_esp)], ['O/E', (x) => (x.o_e != null ? `${num(x.o_e)} (${pval(x.p_aj)})` : '—')], ['Burst', (x) => (x.burst != null ? `${num(x.burst)} · p${x.pct_burst?.toFixed(0) ?? '—'}` : '—')],
            ]} />
          </Card>
          <Card title={`Bloqueadores (${r.bloqueadores.length})`} subtitle="Ordenados por efectividad ajustada · comparaciones contra la media de su posición en la liga">
            <Jugadores rows={r.bloqueadores} onPlayer={onPlayer} cols={[
              ['Bloqueos', (x) => x.snaps], ['Pres. perm.', (x) => x.permitidas], ['Perdidos', (x) => x.perdidos],
              ['Efectividad [IC95]', (x) => `${pct(x.efectividad)} [${pct(x.ic_lo, 0)}–${pct(x.ic_hi, 0)}]`], ['Ajustada', (x) => `${pct(x.efectividad_ajustada)} · p${x.pct?.toFixed(0) ?? '—'}`],
            ]} />
          </Card>
          <Note>{r.a_revisar} jugadores tienen al menos una nota «Evaluar». Las notas de explosividad comparan el burst mediano con los demás jugadores de su posición. Un burst bajo no implica bajo rendimiento: revisa siempre la columna O/E junto con la tasa de presión.</Note>
        </>
      )}
    </div>
  )
}

function Situaciones({ titulo, sub, rows, mejor }: { titulo: string; sub: string; rows: any[]; mejor: 'alto' | 'bajo' }) {
  return (
    <Card title={titulo} subtitle={sub}>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-slate-500"><th>Situación</th><th className="text-right">n</th><th className="text-right">Equipo [IC95]</th><th className="text-right">Liga</th><th className="pl-2">Lectura</th></tr></thead>
        <tbody>{rows.map((s: any) => {
          const fuera = s.ic_lo !== null && (s.liga < s.ic_lo || s.liga > s.ic_hi)
          const bueno = mejor === 'alto' ? s.tasa > s.liga : s.tasa < s.liga
          return (
            <tr key={s.situacion} className="border-t border-slate-100">
              <td className="py-1">{s.situacion}</td><td className="text-right">{s.n}</td>
              <td className="text-right tabular-nums">{pct(s.tasa)} <span className="text-slate-400">[{pct(s.ic_lo, 0)}–{pct(s.ic_hi, 0)}]</span></td>
              <td className="text-right tabular-nums text-slate-500">{pct(s.liga)}</td>
              <td className="pl-2">{fuera ? <Badge color={bueno ? 'green' : 'red'}>{bueno ? 'Mejor que la liga' : 'Peor que la liga'}</Badge> : <span className="text-[11px] text-slate-400">dentro del IC95</span>}</td>
            </tr>
          )
        })}</tbody>
      </table>
    </Card>
  )
}

function Jugadores({ rows, cols, onPlayer }: { rows: any[]; cols: [string, (x: any) => any][]; onPlayer: (id: number) => void }) {
  if (!rows.length) return <p className="text-sm text-slate-500">Sin jugadores que cumplan el mínimo.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-1">Jugador</th>{cols.map(([l]) => <th key={l} className="text-right">{l}</th>)}<th className="pl-3">Notas</th></tr></thead>
        <tbody>{rows.map((x) => (
          <tr key={x.nflId} className="border-b border-slate-100 align-top">
            <td className="py-1.5"><button className="font-medium text-slate-800 hover:underline" onClick={() => onPlayer(x.nflId)}>{x.nombre}</button> <span className="text-slate-400">{x.pos} · {x.peso} lb</span></td>
            {cols.map(([l, f]) => <td key={l} className="whitespace-nowrap text-right tabular-nums">{f(x)}</td>)}
            <td className="pl-3"><div className="flex flex-col gap-0.5">{x.notas.length ? x.notas.map((n: any, i: number) => (
              <span key={i} className="flex items-start gap-1"><Badge color={NOTA[n.tipo]?.color ?? 'slate'}>{NOTA[n.tipo]?.label ?? n.tipo}</Badge><span className="text-slate-600">{n.texto}</span></span>
            )) : <span className="text-slate-400">Sin notas: rendimiento dentro del rango habitual de su posición</span>}</div></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}
