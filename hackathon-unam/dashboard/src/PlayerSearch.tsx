import { useMemo, useState } from 'react'

export type JugadorLista = { nflId: number; displayName: string; officialPosition: string; teams: string; rush: number; block: number; grupo: string }

export default function PlayerSearch({ lista, onPick, filtro, placeholder = 'Buscar jugador…', label }: {
  lista: JugadorLista[]; onPick: (p: JugadorLista) => void; filtro?: (p: JugadorLista) => boolean; placeholder?: string; label?: string
}) {
  const [q, setQ] = useState('')
  const matches = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (t.length < 2) return []
    return lista.filter((p) => (!filtro || filtro(p)) && (p.displayName.toLowerCase().includes(t) || p.teams.toLowerCase().includes(t) || p.officialPosition.toLowerCase() === t)).slice(0, 12)
  }, [q, lista, filtro])
  return (
    <div className="relative w-full">
      {label && <label className="text-xs font-medium text-slate-600">{label}</label>}
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none" />
      {matches.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {matches.map((p) => (
            <li key={p.nflId}>
              <button className="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50" onClick={() => { onPick(p); setQ('') }}>
                <span className="font-medium">{p.displayName}</span> <span className="text-xs text-slate-500">{p.officialPosition} · {p.teams}</span>
                <span className="ml-2 text-[11px] text-slate-400">{p.rush ? `${p.rush} rush` : ''}{p.block ? ` ${p.block} bloq.` : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
