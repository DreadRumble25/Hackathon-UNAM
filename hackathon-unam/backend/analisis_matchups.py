"""Análisis de viabilidad: NFL Matchup Analytics (solo lectura sobre data/).

Uso: .venv\\Scripts\\python backend\\analisis_matchups.py > salida.txt
Todo se calcula en memoria sobre copias; no se escribe nada en data/.
"""
import glob
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 300)

RAIZ = Path(__file__).resolve().parent.parent
D = next(RAIZ.glob("data/**/games.csv")).parent

SNAP = {"ball_snap", "autoevent_ballsnap"}
FIN = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run",
       "pass_tipped", "fumble", "autoevent_passinterrupted"}
MIN_SNAPS = 100


def h(t):
    print("\n" + "=" * 110 + f"\n{t}\n" + "=" * 110, flush=True)


def corr(x, y):
    """Pearson y Spearman con p-valor aproximado (transformación de Fisher)."""
    m = x.notna() & y.notna()
    x, y = x[m].astype(float), y[m].astype(float)
    n = len(x)
    if n < 10:
        return dict(n=n, pearson=np.nan, p_pearson=np.nan, spearman=np.nan, p_spearman=np.nan)
    out = {"n": n}
    for name, a, b in [("pearson", x, y), ("spearman", x.rank(), y.rank())]:
        r = float(np.corrcoef(a, b)[0, 1])
        z = math.atanh(min(max(r, -0.999999), 0.999999)) * math.sqrt(n - 3)
        out[name] = round(r, 3)
        out["p_" + name] = round(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))), 4)
    return out


def shrink(k, n, prior_mean):
    """Shrinkage beta-binomial (método de momentos) hacia la media de la posición."""
    p = k / n
    var_obs = np.average((p - prior_mean) ** 2, weights=n)
    var_bin = np.average(prior_mean * (1 - prior_mean) / n, weights=n)
    var_true = max(var_obs - var_bin, 1e-6)
    m = prior_mean * (1 - prior_mean) / var_true - 1  # fuerza del prior (pseudo-snaps)
    m = max(m, 1.0)
    return (k + m * prior_mean) / (n + m), m


# ============================================================ CARGA
games = pd.read_csv(D / "games.csv")
players = pd.read_csv(D / "players.csv")
plays = pd.read_csv(D / "plays.csv")
pff = pd.read_csv(D / "pffScoutingData.csv")

pl = players.copy()
ht = pl.height.str.split("-", expand=True).astype(int)
pl["height_in"] = ht[0] * 12 + ht[1]
pl = pl[["nflId", "displayName", "officialPosition", "height_in", "weight"]]

h("1. INVENTARIO BÁSICO")
print("partidos:", games.gameId.nunique(), "| jugadas:", len(plays), "| jugadores:", players.nflId.nunique(),
      "| filas PFF:", len(pff))
print("Equipos:", len(set(games.homeTeamAbbr) | set(games.visitorTeamAbbr)))
print("\nRoles PFF (filas = jugador-jugada):")
print(pff.pff_role.value_counts().to_string())
print("\nJugadores únicos por rol:")
print(pff.groupby("pff_role").nflId.nunique().to_string())
print("\nofficialPosition por rol (top):")
print(pd.crosstab(pff.merge(pl, on="nflId").officialPosition, pff.pff_role).to_string())

# ============================================================ FÍSICO POR POSICIÓN
h("2. VARIABILIDAD FÍSICA POR POSICIÓN (players.csv)")
fis = pl.groupby("officialPosition").agg(n=("nflId", "size"),
                                         peso_media=("weight", "mean"), peso_mediana=("weight", "median"),
                                         peso_std=("weight", "std"), alt_media=("height_in", "mean"),
                                         alt_std=("height_in", "std"))
fis["peso_CV%"] = fis.peso_std / fis.peso_media * 100
fis["alt_CV%"] = fis.alt_std / fis.alt_media * 100
print(fis.round(2).sort_values("peso_CV%", ascending=False).to_string())

# ============================================================ ATRIBUCIÓN PFF
h("3. ATRIBUCIÓN DE INDICADORES PFF")
rush = pff[pff.pff_role == "Pass Rush"].copy()
blk = pff[pff.pff_nflIdBlockedPlayer.notna() | (pff.pff_role == "Pass Block")].copy()
for c in ["pff_hit", "pff_hurry", "pff_sack"]:
    rush[c] = rush[c].fillna(0).astype(int)
rush["pressure"] = rush[["pff_hit", "pff_hurry", "pff_sack"]].max(axis=1)
print("Combinaciones hurry/hit/sack por pass-rusher-jugada (filas con alguna marca):")
comb = rush.groupby(["pff_hurry", "pff_hit", "pff_sack"]).size()
print(comb.to_string())
cov = pff[pff.pff_role == "Coverage"]
print("\nCoverage con alguna marca de presión (blitz no etiquetado como rush):",
      int((cov[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).sum(axis=1) > 0).sum()))

# sacks por jugada vs passResult
sk = pff.groupby(["gameId", "playId"]).pff_sack.sum().rename("sacks_pff").reset_index().merge(
    plays[["gameId", "playId", "passResult"]])
print("\nSacks PFF acreditados por jugada vs passResult:")
print(pd.crosstab(sk.sacks_pff, sk.passResult).to_string())

# ============================================================ ENFRENTAMIENTOS
h("4. ENFRENTAMIENTOS BLOQUEADOR -> DEFENSOR (pff_nflIdBlockedPlayer)")
b = pff[pff.pff_nflIdBlockedPlayer.notna()].copy()
b["defId"] = b.pff_nflIdBlockedPlayer.astype(int)
for c in ["pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]:
    b[c] = b[c].fillna(0).astype(int)
b["allowed"] = b[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]].max(axis=1)
dcols = ["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp", "pff_hit", "pff_hurry", "pff_sack"]
dd = pff[dcols].rename(columns={"nflId": "defId", "pff_role": "def_role", "pff_positionLinedUp": "def_lined",
                                "pff_hit": "d_hit", "pff_hurry": "d_hurry", "pff_sack": "d_sack"})
mu = b.merge(dd, on=["gameId", "playId", "defId"], how="left")
mu = mu.merge(pl.add_prefix("blk_"), left_on="nflId", right_on="blk_nflId", how="left")
mu = mu.merge(pl.add_prefix("def_"), left_on="defId", right_on="def_nflId", how="left")
mu["d_pressure"] = mu[["d_hit", "d_hurry", "d_sack"]].fillna(0).max(axis=1)
print("Filas bloqueador-jugada con defensor asignado:", len(mu))
print("Defensor no encontrado en la misma jugada:", mu.def_role.isna().sum())
print("Parejas únicas (bloqueador, defensor):", mu.groupby(["nflId", "defId"]).ngroups)
print("Bloqueadores únicos:", mu.nflId.nunique(), "| defensores únicos:", mu.defId.nunique())
print("Jugadas con al menos un enfrentamiento:", mu.groupby(["gameId", "playId"]).ngroups)
print("\nRol del bloqueador:", mu.pff_role.value_counts().to_dict())
print("Rol del defensor bloqueado:", mu.def_role.value_counts(dropna=False).to_dict())
print("\nTipos de bloqueo en enfrentamientos:\n", mu.pff_blockType.value_counts(dropna=False).to_string())
print("\nBloqueadores (pass block) SIN defensor asignado, por blockType:")
nb = pff[(pff.pff_role == "Pass Block") & pff.pff_nflIdBlockedPlayer.isna()]
print(len(nb), nb.pff_blockType.value_counts(dropna=False).to_dict())
print("\nPosición alineada del defensor (top 20):\n", mu.def_lined.value_counts().head(20).to_string())
print("\nofficialPosition del defensor:\n", mu.def_officialPosition.value_counts().to_string())
print("\nofficialPosition del bloqueador:\n", mu.blk_officialPosition.value_counts().to_string())
print("\nEnfrentamientos por pareja (distribución):\n",
      mu.groupby(["nflId", "defId"]).size().describe().round(2).to_string())
top_pairs = mu.groupby(["blk_displayName", "blk_officialPosition", "def_displayName", "def_officialPosition"]).agg(
    snaps=("playId", "size"), allowed=("allowed", "sum"), beaten=("pff_beatenByDefender", "sum")).sort_values(
    "snaps", ascending=False).head(15)
print("\nParejas más frecuentes:\n", top_pairs.to_string())
print("\nBloqueadores con más enfrentamientos:\n",
      mu.groupby(["blk_displayName", "blk_officialPosition"]).size().sort_values(ascending=False).head(10).to_string())
print("\nDefensores más bloqueados:\n",
      mu.groupby(["def_displayName", "def_officialPosition"]).size().sort_values(ascending=False).head(10).to_string())
print("\nDobles equipos: defensores con >=2 bloqueadores en la misma jugada:",
      int((mu.groupby(["gameId", "playId", "defId"]).size() >= 2).sum()),
      "de", mu.groupby(["gameId", "playId", "defId"]).ngroups, "defensor-jugada bloqueados")

h("4b. CONSISTENCIA DE ATRIBUCIÓN EN ENFRENTAMIENTOS")
mu_a = mu[mu.allowed == 1]
print("Bloqueos con presión permitida:", len(mu_a))
print("  ...y el defensor asignado tiene presión registrada:", int(mu_a.d_pressure.sum()),
      f"({mu_a.d_pressure.mean() * 100:.1f}%)")
for a, d in [("pff_hurryAllowed", "d_hurry"), ("pff_hitAllowed", "d_hit"), ("pff_sackAllowed", "d_sack")]:
    s = mu[mu[a] == 1]
    print(f"  {a}=1: {len(s)}, defensor asignado con {d}=1: {int(s[d].fillna(0).sum())}")
rp = rush[rush.pressure == 1].merge(
    mu[mu.allowed == 1][["gameId", "playId", "defId"]].drop_duplicates().rename(columns={"defId": "nflId"}),
    how="left", indicator=True)
print("Presiones de pass rushers con un bloqueador que la 'permitió' asignado a él:",
      int((rp._merge == "both").sum()), "de", len(rp),
      "| sin bloqueador responsable (no bloqueado, otro bloqueador, o QB):", int((rp._merge == "left_only").sum()))
rushed_blocked = rush.merge(mu[["gameId", "playId", "defId"]].drop_duplicates().rename(columns={"defId": "nflId"}),
                            how="left", indicator=True)
print("Pass-rush snaps donde el rusher tiene al menos un bloqueador asignado:",
      int((rushed_blocked._merge == "both").sum()), "de", len(rush))
ub = rushed_blocked[rushed_blocked._merge == "left_only"]
print("  presión cuando NO tiene bloqueador asignado:", f"{ub.pressure.mean() * 100:.1f}%",
      "| cuando SÍ:", f"{rushed_blocked[rushed_blocked._merge == 'both'].pressure.mean() * 100:.1f}%")

# ============================================================ TASAS POR JUGADOR
h("5. TASAS POR JUGADOR (denominador = jugadas, no frames)")
r_pl = rush.groupby("nflId").agg(rush_snaps=("playId", "size"), pressures=("pressure", "sum"),
                                 hurries=("pff_hurry", "sum"), hits=("pff_hit", "sum"),
                                 sacks=("pff_sack", "sum")).reset_index().merge(pl, on="nflId")
r_pl["pressure_rate"] = r_pl.pressures / r_pl.rush_snaps
pb = pff[pff.pff_role == "Pass Block"].copy()
for c in ["pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]:
    pb[c] = pb[c].fillna(0).astype(int)
pb["allowed"] = pb[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]].max(axis=1)
pb["lost"] = pb[["allowed", "pff_beatenByDefender"]].max(axis=1)
b_pl = pb.groupby("nflId").agg(block_snaps=("playId", "size"), allowed=("allowed", "sum"),
                               beaten=("pff_beatenByDefender", "sum"), lost=("lost", "sum"),
                               sacks_allowed=("pff_sackAllowed", "sum")).reset_index().merge(pl, on="nflId")
b_pl["allowed_rate"] = b_pl.allowed / b_pl.block_snaps
b_pl["effective_rate"] = 1 - b_pl.lost / b_pl.block_snaps
print("Definiciones:")
print("  pressure_rate  = jugadas con hurry|hit|sack / jugadas con pff_role='Pass Rush'")
print("  allowed_rate   = jugadas con hurry|hit|sack allowed / jugadas con pff_role='Pass Block'")
print("  effective_rate = 1 - jugadas con (allowed | beatenByDefender) / jugadas 'Pass Block'")
print(f"\nPass rushers: {len(r_pl)} | con >= {MIN_SNAPS} snaps: {(r_pl.rush_snaps >= MIN_SNAPS).sum()}")
print("rush_snaps:", r_pl.rush_snaps.describe().round(1).to_dict())
print(f"Bloqueadores: {len(b_pl)} | con >= {MIN_SNAPS} snaps: {(b_pl.block_snaps >= MIN_SNAPS).sum()}")
print("block_snaps:", b_pl.block_snaps.describe().round(1).to_dict())
print("\nTasa de presión por officialPosition (rushers >= MIN_SNAPS):")
rq = r_pl[r_pl.rush_snaps >= MIN_SNAPS]
print(rq.groupby("officialPosition").agg(n=("nflId", "size"), snaps=("rush_snaps", "sum"),
                                         tasa_media=("pressure_rate", "mean"),
                                         tasa_mediana=("pressure_rate", "median"),
                                         tasa_std=("pressure_rate", "std"),
                                         peso=("weight", "mean")).round(3).to_string())
print("\nTasa agregada por posición (todos los snaps):")
print(r_pl.groupby("officialPosition")[["rush_snaps", "pressures"]].sum().assign(
    tasa=lambda x: x.pressures / x.rush_snaps).sort_values("rush_snaps", ascending=False).round(3).to_string())
bq = b_pl[b_pl.block_snaps >= MIN_SNAPS]
print("\nBloqueo por officialPosition (>= MIN_SNAPS):")
print(bq.groupby("officialPosition").agg(n=("nflId", "size"), snaps=("block_snaps", "sum"),
                                         allowed_media=("allowed_rate", "mean"),
                                         effective_media=("effective_rate", "mean"),
                                         effective_std=("effective_rate", "std"),
                                         peso=("weight", "mean")).round(3).to_string())

# ============================================================ TRACKING
h("6. MÉTRICAS FÍSICAS DESDE TRACKING (ventana snap -> pase/sack/scramble)")
qb = pff[pff.pff_role == "Pass"][["gameId", "playId", "nflId"]].rename(columns={"nflId": "qbId"})
role = pff[["gameId", "playId", "nflId", "pff_role"]]
aggs, ratio_samples = [], []
win_info = []
for i, t in enumerate(sorted(glob.glob(str(D / "tracking" / "tracking_*.csv")))):
    df = pd.read_csv(t, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "s", "a", "dis", "event"])
    gid = df.gameId.iloc[0]
    e = df[df.event.notna()]
    snap = e[e.event.isin(SNAP)].groupby("playId").frameId.min().rename("snap")
    fin = e[e.event.isin(FIN)].groupby("playId").frameId.min().rename("fin")
    last = df.groupby("playId").frameId.max().rename("last")
    w = pd.concat([snap, fin, last], axis=1).reset_index()
    w["fin_fallback"] = w.fin.isna()
    w["fin"] = w.fin.fillna(w["last"])
    w["gameId"] = gid
    win_info.append(w)
    p = df[df.nflId.notna()].merge(w[["playId", "snap", "fin"]], on="playId")
    p = p[(p.frameId >= p.snap) & (p.frameId <= p.fin)].sort_values(["playId", "nflId", "frameId"])
    p["nflId"] = p.nflId.astype(int)
    # distancia desde coordenadas, solo entre frames consecutivos del mismo jugador y jugada
    g = p.groupby(["playId", "nflId"])
    step = np.hypot(g.x.diff(), g.y.diff())
    contiguous = g.frameId.diff() == 1
    p["step"] = step.where(contiguous, 0.0).fillna(0.0)
    p["rel"] = p.frameId - p.snap
    # distancia al QB
    q = qb[qb.gameId == gid]
    qxy = p.merge(q, on="playId").query("nflId == qbId")[["playId", "frameId", "x", "y"]].rename(
        columns={"x": "qx", "y": "qy"})
    p = p.merge(qxy, on=["playId", "frameId"], how="left")
    p["dqb"] = np.hypot(p.x - p.qx, p.y - p.qy)
    m = p.s > 1
    ratio_samples.append((p.dis[m] / p.s[m]).sample(min(5000, int(m.sum())), random_state=i))
    first = p[p.rel <= 10]
    a1 = p.groupby(["playId", "nflId"]).agg(
        frames=("frameId", "size"), s_max=("s", "max"), s_mean=("s", "mean"), s_std=("s", "std"),
        a_max=("a", "max"), a_mean=("a", "mean"), dist_xy=("step", "sum"), dist_dis=("dis", "sum"),
        dqb_start=("dqb", "first"), dqb_min=("dqb", "min"))
    a2 = first.groupby(["playId", "nflId"]).agg(s_max_1s=("s", "max"))
    a = a1.join(a2).reset_index()
    a["gameId"] = gid
    aggs.append(a)
    if i % 30 == 0:
        print(f"  ...{i + 1}/122", flush=True)

pp = pd.concat(aggs, ignore_index=True).merge(role, on=["gameId", "playId", "nflId"], how="left")
W = pd.concat(win_info, ignore_index=True)
print("Jugadas:", len(W), "| sin snap:", int(W.snap.isna().sum()), "| sin evento de fin (se usa último frame):",
      int(W.fin_fallback.sum()))
W["dur"] = (W.fin - W.snap) / 10
print("Duración ventana snap->fin (s, asumiendo 10 Hz):", W.dur.describe().round(2).to_dict())
rs = pd.concat(ratio_samples)
print("Verificación frecuencia: mediana dis/s =", round(float(rs.median()), 4),
      "(0.1 => 10 frames/s) | p5-p95:", rs.quantile([0.05, 0.95]).round(3).tolist())
print("Filas jugador-jugada con métricas:", len(pp))
print("Corr dist_xy vs dist_dis:", round(float(pp[["dist_xy", "dist_dis"]].corr().iloc[0, 1]), 4))
print("\nMétricas por rol (mediana por jugador-jugada):")
print(pp.groupby("pff_role")[["frames", "s_max", "s_mean", "s_std", "a_max", "a_mean", "dist_xy", "s_max_1s",
                               "dqb_start", "dqb_min"]].median().round(2).to_string())
print("\nPercentil 99.9 de s_max / a_max por rol (valores extremos):")
print(pp.groupby("pff_role")[["s_max", "a_max"]].quantile(0.999).round(2).to_string())
print("Jugador-jugada con s_max > 11 yd/s:", int((pp.s_max > 11).sum()), "| a_max > 12:", int((pp.a_max > 12).sum()))

# ============================================================ JUGADA: FÍSICO vs PRESIÓN
h("7. NIVEL JUGADA: FÍSICO DEL RUSHER vs PRESIÓN (cuidado: confundido por duración)")
rr = rush.merge(pp, on=["gameId", "playId", "nflId"]).merge(pl, on="nflId")
rr["dur"] = rr.frames / 10
print("Filas rusher-jugada con tracking:", len(rr))
print("Duración media con presión vs sin presión (s):",
      rr.groupby("pressure").dur.mean().round(2).to_dict())
for c in ["s_max_1s", "s_max", "a_max", "dqb_min"]:
    rr["q"] = pd.qcut(rr[c], 5, labels=False, duplicates="drop")
    t = rr.groupby("q").agg(lo=(c, "min"), hi=(c, "max"), n=("pressure", "size"), tasa=("pressure", "mean"),
                            dur=("dur", "mean"))
    print(f"\nQuintiles de {c}:\n", t.round(3).to_string())
# controlando duración: dentro de terciles de duración
rr["dur_t"] = pd.qcut(rr.dur, 3, labels=["corta", "media", "larga"])
rr["burst_q"] = rr.groupby("dur_t", observed=True).s_max_1s.transform(lambda v: pd.qcut(v, 4, labels=False))
print("\nTasa de presión por cuartil de s_max_1s DENTRO de cada tercil de duración:")
print(rr.pivot_table(index="burst_q", columns="dur_t", values="pressure", aggfunc="mean", observed=True).round(3).to_string())

# ============================================================ JUGADOR: FÍSICO vs RENDIMIENTO
h("8. NIVEL JUGADOR: FÍSICO vs RENDIMIENTO")
phys = pp.groupby("nflId").agg(plays_trk=("playId", "size"), s_max_p95=("s_max", lambda v: v.quantile(0.95)),
                               s_max_med=("s_max", "median"), a_max_p95=("a_max", lambda v: v.quantile(0.95)),
                               a_max_med=("a_max", "median"), s_mean=("s_mean", "mean"),
                               s_std=("s_std", "mean"), dist_med=("dist_xy", "median"),
                               burst_med=("s_max_1s", "median")).reset_index()
rush_phys = rr.groupby("nflId").agg(burst_rush=("s_max_1s", "median"), smax_rush=("s_max", "median"),
                                    amax_rush=("a_max", "median"), dqb_min_med=("dqb_min", "median")).reset_index()
R = rq.merge(phys, on="nflId").merge(rush_phys, on="nflId")
R["momentum"] = R.weight * R.burst_rush
grp = {"DE": "EDGE", "OLB": "EDGE", "DT": "IDL", "NT": "IDL"}
R["grupo"] = R.officialPosition.map(grp).fillna("OTRO")
pm = R.groupby("grupo").pressures.sum() / R.groupby("grupo").rush_snaps.sum()
R["rate_shrunk"] = np.nan
for g_, sub in R.groupby("grupo"):
    s_, mstr = shrink(sub.pressures.values, sub.rush_snaps.values, pm[g_])
    R.loc[sub.index, "rate_shrunk"] = s_
    print(f"Prior {g_}: tasa={pm[g_]:.3f}, fuerza={mstr:.0f} snaps, n={len(sub)}")
print("Rushers analizados (>=100 snaps):", len(R), R.grupo.value_counts().to_dict())
feats = ["weight", "height_in", "burst_rush", "smax_rush", "amax_rush", "s_max_p95", "a_max_p95", "momentum",
         "dqb_min_med"]
rows = []
for g_ in ["TODOS", "EDGE", "IDL"]:
    sub = R if g_ == "TODOS" else R[R.grupo == g_]
    for f in feats:
        rows.append({"grupo": g_, "variable": f, **corr(sub[f], sub.pressure_rate)})
print("\nCorrelación con pressure_rate (rushers):\n", pd.DataFrame(rows).to_string(index=False))
# z dentro de posición
for f in ["weight", "height_in", "burst_rush", "a_max_p95"]:
    R["z_" + f] = R.groupby("officialPosition")[f].transform(lambda v: (v - v.mean()) / v.std())
R["z_rate"] = R.groupby("officialPosition").pressure_rate.transform(lambda v: (v - v.mean()) / v.std())
rows = [{"variable": "z_" + f, **corr(R["z_" + f], R.z_rate)} for f in ["weight", "height_in", "burst_rush", "a_max_p95"]]
print("\nCorrelación usando z-scores dentro de officialPosition (elimina efecto posición):\n",
      pd.DataFrame(rows).to_string(index=False))
print("\nTercil de burst_rush dentro de EDGE vs tasa:")
e_ = R[R.grupo == "EDGE"].copy()
e_["t"] = pd.qcut(e_.burst_rush, 3, labels=["bajo", "medio", "alto"])
print(e_.groupby("t", observed=True).agg(n=("nflId", "size"), burst=("burst_rush", "mean"),
                                         tasa_media=("pressure_rate", "mean"),
                                         tasa_mediana=("pressure_rate", "median"), peso=("weight", "mean")).round(3).to_string())
i_ = R[R.grupo == "IDL"].copy()
i_["t"] = pd.qcut(i_.weight, 3, labels=["ligero", "medio", "pesado"])
print("\nTercil de peso dentro de IDL vs tasa:")
print(i_.groupby("t", observed=True).agg(n=("nflId", "size"), peso=("weight", "mean"),
                                         tasa_media=("pressure_rate", "mean"),
                                         burst=("burst_rush", "mean")).round(3).to_string())

# Bloqueadores
blk_phys = pp[pp.pff_role == "Pass Block"].groupby("nflId").agg(
    smax_blk=("s_max", "median"), amax_blk=("a_max", "median"), dist_blk=("dist_xy", "median")).reset_index()
B = bq.merge(blk_phys, on="nflId")
B["grupo"] = B.officialPosition.map({"T": "OT", "G": "IOL", "C": "IOL"}).fillna("OTRO")
pmb = 1 - B.groupby("grupo").lost.sum() / B.groupby("grupo").block_snaps.sum()
B["eff_shrunk"] = np.nan
for g_, sub in B.groupby("grupo"):
    s_, mstr = shrink(sub.block_snaps.values - sub.lost.values, sub.block_snaps.values, pmb[g_])
    B.loc[sub.index, "eff_shrunk"] = s_
    print(f"Prior bloqueo {g_}: efectividad={pmb[g_]:.3f}, fuerza={mstr:.0f}, n={len(sub)}")
rows = []
for g_ in ["TODOS", "OT", "IOL"]:
    sub = B if g_ == "TODOS" else B[B.grupo == g_]
    for f in ["weight", "height_in", "smax_blk", "amax_blk", "dist_blk"]:
        rows.append({"grupo": g_, "variable": f, **corr(sub[f], sub.effective_rate)})
print("\nCorrelación con effective_rate (bloqueadores >=100 snaps):\n", pd.DataFrame(rows).to_string(index=False))

# ============================================================ ENFRENTAMIENTO: DIFERENCIAS FÍSICAS
h("9. NIVEL ENFRENTAMIENTO: DIFERENCIA FÍSICA DEFENSOR - BLOQUEADOR")
M = mu[(mu.pff_role == "Pass Block") & (mu.def_role == "Pass Rush")].copy()
M = M[M.blk_officialPosition.isin(["T", "G", "C"])]
M["d_weight"] = M.def_weight - M.blk_weight
M["d_height"] = M.def_height_in - M.blk_height_in
M["lost"] = M[["allowed", "pff_beatenByDefender"]].max(axis=1)
M = M.merge(pp[["gameId", "playId", "nflId", "s_max_1s"]].rename(columns={"nflId": "defId", "s_max_1s": "def_burst"}),
            on=["gameId", "playId", "defId"], how="left")
print("Enfrentamientos OL vs pass rusher:", len(M), "| tasa de bloqueo perdido:", round(M.lost.mean(), 4))
for c, bins in [("d_weight", [-200, -60, -30, 0, 30, 200]), ("d_height", [-20, -3, -1, 1, 3, 20])]:
    M["bin"] = pd.cut(M[c], bins)
    print(f"\n{c}:\n", M.groupby("bin", observed=True).agg(n=("lost", "size"), perdido=("lost", "mean"),
                                                         permitido=("allowed", "mean")).round(4).to_string())
M["bq"] = pd.qcut(M.def_burst, 5, labels=False)
print("\nQuintil de burst del defensor (1er segundo) en el enfrentamiento:\n",
      M.groupby("bq").agg(lo=("def_burst", "min"), hi=("def_burst", "max"), n=("lost", "size"),
                          perdido=("lost", "mean")).round(4).to_string())
print("\nPor tipo de bloqueo:\n", M.groupby("pff_blockType").agg(n=("lost", "size"), perdido=("lost", "mean"),
                                                               permitido=("allowed", "mean")).sort_values(
    "n", ascending=False).round(4).to_string())
print("\nPor posición OL vs grupo defensor:\n",
      M.assign(dg=M.def_officialPosition.map(grp).fillna("OTRO")).pivot_table(
          index="blk_officialPosition", columns="dg", values="lost", aggfunc=["mean", "size"]).round(4).to_string())
pairs = M.groupby(["nflId", "defId"]).size()
print("\nParejas OL-rusher con >=5 / >=10 / >=20 enfrentamientos:",
      int((pairs >= 5).sum()), int((pairs >= 10).sum()), int((pairs >= 20).sum()), "de", len(pairs))

# ============================================================ DESTACADOS
h("10. JUGADORES DESTACADOS")
cols = ["displayName", "officialPosition", "weight", "height_in", "rush_snaps", "pressures", "sacks",
        "pressure_rate", "rate_shrunk", "burst_rush"]
print("Top 15 pass rushers (tasa con shrinkage):\n",
      R.sort_values("rate_shrunk", ascending=False)[cols].head(15).round(3).to_string(index=False))
bcols = ["displayName", "officialPosition", "weight", "height_in", "block_snaps", "allowed", "beaten",
         "effective_rate", "eff_shrunk"]
print("\nTop 15 bloqueadores (efectividad con shrinkage):\n",
      B.sort_values("eff_shrunk", ascending=False)[bcols].head(15).round(3).to_string(index=False))
print("\nBottom 10 bloqueadores:\n",
      B.sort_values("eff_shrunk")[bcols].head(10).round(3).to_string(index=False))
R["rank_pos"] = R.groupby("grupo").rate_shrunk.rank(pct=True)
avg_phys = R[(R.z_weight.abs() < 0.75) & (R.z_burst_rush.abs() < 0.75) & (R.rank_pos >= 0.85)]
print("\nRushers con peso y explosividad cercanos a la media de su posición (|z|<0.75) y tasa en top 15% de su grupo:\n",
      avg_phys[cols + ["z_weight", "z_burst_rush"]].round(3).to_string(index=False))
top = R[R.rank_pos >= 0.8]
rest = R[R.rank_pos < 0.8]
print("\nTop 20% vs resto (medias de z dentro de posición):")
print(pd.DataFrame({"top20": top[["z_weight", "z_height_in", "z_burst_rush", "z_a_max_p95"]].mean(),
                    "resto": rest[["z_weight", "z_height_in", "z_burst_rush", "z_a_max_p95"]].mean()}).round(3).to_string())
print("\nAtípicos físicos (|z|>2.5 dentro de posición):")
for f in ["weight", "height_in", "burst_rush"]:
    o = R[R["z_" + f].abs() > 2.5]
    print(f" {f}:", o[["displayName", "officialPosition", f]].round(2).values.tolist())
print("\nFIN", flush=True)
