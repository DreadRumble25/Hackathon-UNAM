import { ReactNode, useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ComposedChart, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { Card, Loading, Note, int, num, pct } from '../ui'

export default function Metodologia() {
  const [lab, setLab] = useState<any>(null)
  useEffect(() => { api('laboratorio').then(setLab).catch(() => setLab(null)) }, [])
  if (!lab) return <Loading />
  const a = lab.ajuste
  const [A, , C] = lab.quintiles_versiones
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Sec t="1. Datos">
          <p>NFL Big Data Bowl (datos del evento; mismo formato que la edición 2023 en Kaggle): temporada 2021, semanas 1–8, <b>solo jugadas de pase</b> (dropbacks). Se combinan:</p>
          <ul>
            <li><b>Tracking</b> de Next Gen Stats a 10 Hz (verificado: la mediana de <code>dis/s</code> es 0.100 s). Columnas <code>x, y, s, a, dis, o, dir, frameId, event</code>.</li>
            <li><b>PFF scouting</b>: rol del jugador en la jugada, alineación, hurry/hit/sack, presión permitida, defensor bloqueado (<code>pff_nflIdBlockedPlayer</code>) y tipo de bloqueo.</li>
            <li><b>Jugadores</b>: posición oficial, peso y estatura (pulgadas enteras; poca variación dentro de cada posición).</li>
            <li><b>Jugadas y partidos</b>: down, distancia, formación, play action, equipos y semana.</li>
          </ul>
          <p>Los archivos originales nunca se modifican. Todas las tablas derivadas se calculan en memoria al arrancar el servidor.</p>
        </Sec>
        <Sec t="2. Unidad de análisis y denominadores">
          <p>La unidad es <b>jugador × jugada</b>. Los frames del tracking nunca se tratan como observaciones independientes: se resumen en una métrica por jugador y jugada.</p>
          <F>Tasa de presión = jugadas con hurry, hit o sack ÷ jugadas con pff_role = «Pass Rush»</F>
          <F>Efectividad de bloqueo = 1 − (jugadas con presión permitida o beatenByDefender) ÷ jugadas con pff_role = «Pass Block»</F>
          <F>Presión permitida del equipo = dropbacks con ≥1 presión de cualquier defensor ÷ dropbacks</F>
          <p>En PFF, hurry, hit y sack son mutuamente excluyentes para un jugador en una jugada (se registra la consecuencia más grave), así que «presión» nunca se cuenta dos veces. Un enfrentamiento es un bloqueador en una jugada con el defensor que PFF le asigna. Cuando un defensor recibe doble equipo, aparece en dos enfrentamientos.</p>
        </Sec>
        <Sec t="3. Métricas físicas">
          <ul>
            <li><b>Burst</b>: máximo de <code>s</code> (yd/s) en los frames 1–10 después del snap (primer segundo).</li>
            <li><b>Getoff</b>: distancia en línea recta entre la posición en el snap y en el frame 10.</li>
            <li><b>Aceleración máx. 1 s</b>: máximo de <code>a</code> en el mismo intervalo. Ojo: <code>a</code> no tiene signo e incluye los frenados.</li>
            <li><b>Velocidad, aceleración y distancia de la jugada</b>: entre el snap y el primer evento de pase, sack, scramble o fumble. Distancia = suma de √(Δx² + Δy²) entre frames consecutivos del mismo jugador y jugada (coincide con la suma de <code>dis</code>, r = 0.9999).</li>
          </ul>
          <p>Las métricas de toda la jugada dependen de su duración (las jugadas con presión duran más), así que pueden ser consecuencia del resultado. Las del primer segundo ocurren antes de casi todas las presiones. Por eso el análisis principal usa el burst.</p>
          <p>El perfil del jugador muestra la <b>mediana por jugada</b> y su percentil frente a jugadores de la misma posición oficial y el mismo rol con ≥20 jugadas.</p>
        </Sec>
        <Sec t="4. Hallazgo exploratorio vs modelo">
          <p><b>Exploratorio (A)</b>: todos los snaps de pass rush con tracking ({int(A.n)}), incluidos LB y DB en blitz; burst medido entre los frames 0 y 10 dentro de la ventana snap→pase. Quintil inferior {pct(A.q1)} vs superior {pct(A.q5)} ({num(A.razon, 2)}×).</p>
          <p><b>Población del modelo (C)</b>: EDGE e IDL con snap, posición del QB y ventana válida, sin conversiones de 2 puntos ({int(C.n)}); burst en los frames 1–10. Quintil inferior {pct(C.q1)} vs superior {pct(C.q5)} ({num(C.razon, 2)}×).</p>
          <p>Son <b>tasas observadas</b>. El modelo da <b>probabilidades estimadas</b> que controlan otras variables. Las dos cosas responden preguntas distintas y la app las etiqueta siempre por separado.</p>
        </Sec>
        <Sec t="5. Modelo logístico M3">
          <F>logit P(presión) = β₀ + β₁·burst + β₂·peso + β₃·IDL + β₄·burst×IDL + β₅·peso×IDL + β₆·dist. al QB + β₇·rushers + β₈·3.er/4.º down + β₉·yardas + β₁₀·play action + β₁₁·shotgun</F>
          <ul>
            <li>Variables continuas centradas en su media. Peso en unidades de 10 lb.</li>
            <li>Ajuste por IRLS (máxima verosimilitud) implementado con NumPy.</li>
            <li><b>Errores estándar robustos agrupados por jugador</b> (sandwich CR1), porque las jugadas de un mismo jugador no son independientes. Son entre 15% y 45% mayores que los ingenuos. Agrupar por partido da resultados similares.</li>
            <li>Bootstrap por jugador (400 réplicas, en <code>backend/analisis_presion.py</code>): IC del OR de burst EDGE 1.29–1.47 e IDL 1.40–1.67.</li>
            <li><b>M4</b> separa el burst habitual del jugador (su promedio) de la desviación en cada jugada.</li>
          </ul>
          <p><b>Tasa esperada</b> de un jugador = suma de las probabilidades de M3 en sus jugadas ÷ número de jugadas. <b>O/E</b> = presiones observadas ÷ esperadas.</p>
          <F>z = (O − E) / √(φ · Σ p(1 − p)),   φ = {num(a.phi)} (sobredispersión entre jugadores)</F>
          <p><b>Tasa ajustada</b>: shrinkage beta-binomial hacia la media del grupo (EDGE, IDL, OT, IOL), con la fuerza del prior estimada por el método de momentos. Así, un jugador con pocas jugadas no aparece arriba por azar.</p>
        </Sec>
        <Sec t="6. Validación">
          <ul>
            <li>Muestra: {int(a.n)} rusher-jugadas, {a.jugadores} jugadores, {a.partidos} partidos.</li>
            <li>AUC {num(a.auc, 3)} (validación cruzada de 5 bloques por jugador: 0.610, sin sobreajuste). R² de McFadden {num(a.mcfadden, 3)}. Brier {num(a.brier, 4)} vs {num(a.brier_base, 4)} de la tasa base.</li>
            <li>Calibración: Hosmer-Lemeshow χ² = {num(a.hosmer_lemeshow, 1)} con 8 gl (crítico al 5% = 15.5).</li>
            <li>Colinealidad: VIF ≤ 4.4 en M3. Getoff y burst no se incluyen juntos (VIF 7.5).</li>
            <li>Sensibilidad: el OR de burst es estable con mínimos de 1 a 200 snaps, al excluir rushers sin bloqueador y al definir el grupo por alineación real.</li>
            <li>Peso: sin efecto propio después de controlar el burst; la correlación simple peso–presión se explica por la relación entre peso y explosividad.</li>
          </ul>
        </Sec>
        <Sec t="7. Limitaciones">
          <ul>
            <li><b>Asociación, no causalidad.</b> El burst también depende del plan de bloqueo, los stunts, las asignaciones y la respuesta del bloqueador, que no están en los datos.</li>
            <li>Solo 8 semanas y solo jugadas de pase. No hay jugadas de carrera ni equipos especiales.</li>
            <li>El modelo explica poco de una jugada individual (AUC {num(a.auc)}). Sirve para promedios y perfiles, no para pronósticos.</li>
            <li>Los rankings de O/E evalúan muchos jugadores a la vez; ninguno sobrevive la corrección de Bonferroni. Son exploratorios.</li>
            <li>El crédito de presión en doble equipo es ambiguo, y 40% de las presiones no tienen un bloqueador responsable asignado.</li>
            <li>No hay brazada, fuerza ni técnica. La estatura tiene baja resolución y la edad falta en 14% de los jugadores.</li>
            <li>24 jugadas no tienen evento de snap y quedan fuera de las métricas físicas.</li>
          </ul>
        </Sec>
      </div>
      <div className="space-y-4">
        <Card title="Calibración del modelo M3" subtitle="Deciles de probabilidad estimada: esperado vs observado">
          <div className="h-64">
            <ResponsiveContainer>
              <ComposedChart data={lab.calibracion}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" dataKey="esperado" domain={[0, 0.22]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} />
                <YAxis type="number" domain={[0, 0.22]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} width={34} />
                <Tooltip formatter={(v: any) => pct(Number(v))} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 0.22, y: 0.22 }]} stroke="#94a3b8" strokeDasharray="4 4" />
                <Scatter dataKey="observado" fill="#7c3aed" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="text-xs text-slate-600">Los puntos siguen la diagonal: las probabilidades estimadas coinciden con las frecuencias reales en promedio.</p>
        </Card>
        <Card title="Robustez del OR de burst (EDGE)" subtitle="Mismo modelo con distintas poblaciones">
          <div className="h-48">
            <ResponsiveContainer>
              <LineChart data={lab.robustez.map((r: any, i: number) => ({ i: i + 1, ...r }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="i" fontSize={10} />
                <YAxis domain={[1, 1.8]} fontSize={10} width={30} />
                <Tooltip formatter={(v: any) => num(Number(v))} labelFormatter={(i: any) => lab.robustez[Number(i) - 1]?.analisis} />
                <ReferenceLine y={1} stroke="#475569" />
                <Line dataKey="or_edge" name="EDGE" stroke="#2563eb" />
                <Line dataKey="or_idl" name="IDL" stroke="#ea580c" />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <ol className="list-inside list-decimal text-[11px] text-slate-500">{lab.robustez.map((r: any) => <li key={r.analisis}>{r.analisis}</li>)}</ol>
        </Card>
        <Note>Código reproducible: <code>backend/exploracion.py</code>, <code>backend/analisis_matchups.py</code>, <code>backend/analisis_presion.py</code> (análisis) y <code>backend/engine.py</code> (motor de la aplicación).</Note>
      </div>
    </div>
  )
}

function Sec({ t, children }: { t: string; children: ReactNode }) {
  return <Card title={t}><div className="prose-sm space-y-2 text-sm leading-relaxed text-slate-700 [&_li]:ml-4 [&_li]:list-disc [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:text-xs">{children}</div></Card>
}
function F({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-xs text-slate-800">{children}</div>
}
