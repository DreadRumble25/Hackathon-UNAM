import { useEffect, useState } from 'react'
import { api } from './api'
import type { JugadorLista } from './PlayerSearch'
import Comparador from './pages/Comparador'
import Control from './pages/Control'
import Enfrentamientos from './pages/Enfrentamientos'
import Laboratorio from './pages/Laboratorio'
import Metodologia from './pages/Metodologia'
import ObservadoEsperado from './pages/ObservadoEsperado'
import Perfil from './pages/Perfil'
import Reportes from './pages/Reportes'
import Simulador from './pages/Simulador'
import { ErrorBox } from './ui'

const TABS = [
  { id: 'control', label: 'Centro de control', q: '¿Cómo están mis jugadores y mi equipo?' },
  { id: 'perfil', label: 'Perfil de jugador', q: '¿Qué tan bueno es y cómo se compara con su posición?' },
  { id: 'lab', label: 'Laboratorio de explosividad', q: '¿Qué tanto importa el primer segundo?' },
  { id: 'oe', label: 'Observado vs esperado', q: '¿Quién produce más de lo que su perfil predice?' },
  { id: 'enf', label: 'Enfrentamientos', q: '¿Quién gana el duelo bloqueador vs pass rusher?' },
  { id: 'comp', label: 'Comparador', q: '¿Cómo se comparan jugadores equivalentes?' },
  { id: 'sim', label: 'Simulador', q: '¿Qué probabilidad estima el modelo en cada escenario?' },
  { id: 'rep', label: 'Reportes', q: 'Resumen por equipo para el cuerpo técnico' },
  { id: 'met', label: 'Metodología', q: 'Cómo se calculó todo y qué límites tiene' },
] as const
type Tab = (typeof TABS)[number]['id']

export default function App() {
  const [estado, setEstado] = useState<any>(null)
  const desdeHash = (): Tab => { const h = window.location.hash.replace('#', '').split('/')[0]; return (TABS.some((t) => t.id === h) ? h : 'control') as Tab }
  const [tab, setTabState] = useState<Tab>(desdeHash)
  const setTab = (t: Tab) => { setTabState(t); if (window.location.hash !== `#${t}`) window.history.replaceState(null, '', `#${t}`) }
  useEffect(() => {
    const f = () => setTabState(desdeHash())
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])
  const [jugador, setJugador] = useState<number | null>(() => { const m = window.location.hash.match(/^#perfil\/(\d+)/); return m ? Number(m[1]) : null })
  const [comparar, setComparar] = useState<number[]>(() => { const m = window.location.hash.match(/^#comp\/([\d,]+)/); return m ? m[1].split(',').map(Number).slice(0, 4) : [] })
  const [lista, setLista] = useState<JugadorLista[]>([])
  const [equipos, setEquipos] = useState<string[]>([])

  useEffect(() => {
    let vivo = true
    const tick = () => api('estado').then((s) => {
      if (!vivo) return
      setEstado(s)
      if (!s.listo && !s.error) setTimeout(tick, 1500)
    }).catch(() => vivo && setTimeout(tick, 2500))
    tick()
    return () => { vivo = false }
  }, [])
  useEffect(() => {
    if (!estado?.listo) return
    api<JugadorLista[]>('jugadores').then(setLista).catch(() => undefined)
    api('filtros').then((f) => setEquipos(f.equipos)).catch(() => undefined)
  }, [estado?.listo])

  const abrirJugador = (id: number) => { setJugador(id); setTabState('perfil'); window.history.replaceState(null, '', `#perfil/${id}`); window.scrollTo({ top: 0 }) }
  const abrirComparador = (id: number) => { setComparar((v) => (v.includes(id) ? v : [id, ...v].slice(0, 4))); setTab('comp'); window.scrollTo({ top: 0 }) }
  const actual = TABS.find((t) => t.id === tab)!

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="bg-slate-900 text-white print:hidden">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3">
          <div>
            <div className="text-lg font-bold tracking-tight">NFL Matchup Analytics</div>
            <div className="text-xs text-slate-400">Bloqueadores vs pass rushers · física del movimiento · modelado estadístico · temporada 2021, semanas 1–8</div>
          </div>
          <div className="text-[11px] text-slate-400">Datos: NFL Big Data Bowl (Next Gen Stats + PFF)</div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-2">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)} className={`whitespace-nowrap rounded-t-md px-3 py-2 text-xs font-medium transition ${tab === t.id ? 'bg-slate-100 text-slate-900' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`}>{t.label}</button>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-4">
        <div className="mb-3 flex items-baseline gap-2 print:hidden"><h1 className="text-base font-bold">{actual.label}</h1><span className="text-xs text-slate-500">{actual.q}</span></div>
        {!estado ? <Preparando etapa="Conectando con el servidor…" progreso={0} /> :
          estado.error ? <ErrorBox error={estado.error} /> :
            !estado.listo ? <Preparando etapa={estado.etapa} progreso={estado.progreso} /> : (
              <>
                {tab === 'control' && <Control onPlayer={abrirJugador} onLab={() => setTab('lab')} />}
                {tab === 'perfil' && <Perfil nflId={jugador} lista={lista} onSelect={abrirJugador} onCompare={abrirComparador} />}
                {tab === 'lab' && <Laboratorio onPlayer={abrirJugador} />}
                {tab === 'oe' && <ObservadoEsperado onPlayer={abrirJugador} equipos={equipos} />}
                {tab === 'enf' && <Enfrentamientos lista={lista} equipos={equipos} onPlayer={abrirJugador} />}
                {tab === 'comp' && <Comparador lista={lista} ids={comparar} setIds={setComparar} onPlayer={abrirJugador} />}
                {tab === 'sim' && <Simulador />}
                {tab === 'rep' && <Reportes equipos={equipos} onPlayer={abrirJugador} />}
                {tab === 'met' && <Metodologia />}
              </>
            )}
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-6 text-[11px] text-slate-500 print:hidden">
        Todas las cifras se calculan con los datos del evento. Las asociaciones estadísticas no implican causalidad. Las tasas observadas y las probabilidades estimadas por el modelo se indican por separado.
      </footer>
    </div>
  )
}

function Preparando({ etapa, progreso }: { etapa: string; progreso: number }) {
  return (
    <div className="mx-auto mt-16 max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
      <div className="text-sm font-semibold text-slate-800">Preparando los datos</div>
      <p className="mt-1 text-xs text-slate-500">El servidor procesa el tracking de 122 partidos y ajusta el modelo al arrancar (unos 20–30 segundos).</p>
      <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-slate-200"><div className="h-2 rounded-full bg-blue-600 transition-all" style={{ width: `${Math.round(progreso * 100)}%` }} /></div>
      <div className="mt-2 text-xs text-slate-500">{etapa} · {Math.round(progreso * 100)}%</div>
    </div>
  )
}
