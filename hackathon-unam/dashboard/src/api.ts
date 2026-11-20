// Todas las rutas son relativas y sin diagonal inicial: la app se publica en una subruta.
export async function api<T = any>(ruta: string, params?: Record<string, string | number | null | undefined>): Promise<T> {
  const q = new URLSearchParams()
  if (params) for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v))
  const url = `api/${ruta}${q.toString() ? `?${q}` : ''}`
  const r = await fetch(url)
  if (!r.ok) {
    let detalle = `${r.status}`
    try { detalle = (await r.json()).detail ?? detalle } catch { /* sin cuerpo JSON */ }
    throw new Error(detalle)
  }
  return r.json() as Promise<T>
}
