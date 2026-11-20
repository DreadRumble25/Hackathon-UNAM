"""Investigación estadística: características físicas y de movimiento vs. presión al QB.

Unidad de análisis: pass-rusher x jugada (nunca frame).
Regresión logística por IRLS (numpy) con errores estándar robustos por clúster
(jugador) y bootstrap por jugador. Solo lectura sobre data/; la tabla derivada
rusher-jugada se guarda como caché en el directorio temporal del sistema.

Uso: .venv\\Scripts\\python backend\\analisis_presion.py > salida.txt
"""
import glob
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 60)
pd.set_option("display.max_rows", 300)

RAIZ = Path(__file__).resolve().parent.parent
D = next(RAIZ.glob("data/**/games.csv")).parent
CACHE = Path(tempfile.gettempdir()) / "nfl_rusher_play_v1.csv"
SNAP = {"ball_snap", "autoevent_ballsnap"}
FIN = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run",
       "pass_tipped", "fumble", "autoevent_passinterrupted"}
GRUPO = {"DE": "EDGE", "OLB": "EDGE", "DT": "IDL", "NT": "IDL"}
ALINEACION = {**{k: "EDGE" for k in ["LEO", "REO", "LE", "RE", "LOLB", "ROLB"]},
              **{k: "IDL" for k in ["DLT", "DRT", "NT", "NLT", "NRT"]}}
RNG = np.random.default_rng(2026)


def h(t):
    print("\n" + "=" * 110 + f"\n{t}\n" + "=" * 110, flush=True)


def ncdf(z):
    return 0.5 * (1 + np.vectorize(math.erf)(np.asarray(z) / math.sqrt(2)))


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    hw = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - hw, c + hw


# ------------------------------------------------------------------ logística
def logit_fit(X, y, max_iter=50, tol=1e-10):
    b = np.zeros(X.shape[1])
    for _ in range(max_iter):
        p = 1 / (1 + np.exp(-(X @ b)))
        W = p * (1 - p)
        H = X.T @ (W[:, None] * X)
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < tol:
            break
    p = 1 / (1 + np.exp(-(X @ b)))
    H = X.T @ ((p * (1 - p))[:, None] * X)
    return b, p, np.linalg.inv(H)


def cluster_vcov(X, y, p, bread, groups):
    u = X * (y - p)[:, None]
    gs = pd.DataFrame(u).groupby(groups).sum().to_numpy()
    G, (N, K) = gs.shape[0], X.shape
    meat = gs.T @ gs
    c = G / (G - 1) * (N - 1) / (N - K)
    return c * bread @ meat @ bread


def auc(y, p):
    r = pd.Series(p).rank().to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


class Modelo:
    def __init__(self, df, cols, nombre, cluster="nflId"):
        self.nombre, self.cols = nombre, cols
        X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(float) for c in cols])
        y = df.pressure.to_numpy(float)
        b, p, bread = logit_fit(X, y)
        self.b, self.p, self.X, self.y = b, p, X, y
        self.V = cluster_vcov(X, y, p, bread, df[cluster].to_numpy())
        self.V_game = cluster_vcov(X, y, p, bread, df["gameId"].to_numpy())
        self.V_naive = bread
        self.ll = float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))
        p0 = y.mean()
        self.ll0 = float(len(y) * (p0 * np.log(p0) + (1 - p0) * np.log(1 - p0)))
        self.n, self.k, self.G = len(y), X.shape[1], df[cluster].nunique()

    def tabla(self):
        names = ["(intercepto)"] + self.cols
        se = np.sqrt(np.diag(self.V))
        se_g = np.sqrt(np.diag(self.V_game))
        se_n = np.sqrt(np.diag(self.V_naive))
        z = self.b / se
        t = pd.DataFrame({"coef": self.b, "OR": np.exp(self.b),
                          "IC95_inf": np.exp(self.b - 1.96 * se), "IC95_sup": np.exp(self.b + 1.96 * se),
                          "SE_jugador": se, "SE_partido": se_g, "SE_naive": se_n,
                          "p_valor": 2 * (1 - ncdf(np.abs(z)))}, index=names)
        return t

    def lincomb(self, w):
        w = np.asarray(w, float)
        est = w @ self.b
        se = math.sqrt(w @ self.V @ w)
        return est, se, 2 * (1 - float(ncdf(abs(est / se))))

    def resumen(self):
        aic = -2 * self.ll + 2 * self.k
        bic = -2 * self.ll + self.k * math.log(self.n)
        return {"modelo": self.nombre, "n": self.n, "jugadores": self.G, "k": self.k,
                "logLik": round(self.ll, 1), "AIC": round(aic, 1), "BIC": round(bic, 1),
                "McFadden_R2": round(1 - self.ll / self.ll0, 4), "AUC": round(auc(self.y, self.p), 4),
                "Brier": round(float(np.mean((self.y - self.p) ** 2)), 5)}


def vif(df, cols):
    out = {}
    for c in cols:
        others = [o for o in cols if o != c]
        A = np.column_stack([np.ones(len(df))] + [df[o].to_numpy(float) for o in others])
        yv = df[c].to_numpy(float)
        coef, *_ = np.linalg.lstsq(A, yv, rcond=None)
        r2 = 1 - np.sum((yv - A @ coef) ** 2) / np.sum((yv - yv.mean()) ** 2)
        out[c] = round(1 / (1 - r2), 2)
    return out


# ============================================================ DATOS
plays = pd.read_csv(D / "plays.csv")
players = pd.read_csv(D / "players.csv")
pff = pd.read_csv(D / "pffScoutingData.csv")
rush = pff[pff.pff_role == "Pass Rush"][["gameId", "playId", "nflId", "pff_positionLinedUp",
                                         "pff_hit", "pff_hurry", "pff_sack"]].copy()
rush["pressure"] = rush[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).max(axis=1).astype(int)
qb = pff[pff.pff_role == "Pass"][["gameId", "playId", "nflId"]].rename(columns={"nflId": "qbId"})

if CACHE.exists():
    T = pd.read_csv(CACHE)
    print("Tabla rusher-jugada cargada de caché:", CACHE)
else:
    parts = []
    for t in sorted(glob.glob(str(D / "tracking" / "tracking_*.csv"))):
        df = pd.read_csv(t, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "s", "a", "event"])
        gid = int(df.gameId.iloc[0])
        e = df[df.event.notna()]
        w = pd.concat([e[e.event.isin(SNAP)].groupby("playId").frameId.min().rename("snap"),
                       e[e.event.isin(FIN)].groupby("playId").frameId.min().rename("fin")], axis=1)
        w = w.dropna(subset=["snap"]).reset_index()
        p = df[df.nflId.notna()].copy()
        p["nflId"] = p.nflId.astype(int)
        p = p.merge(w, on="playId")
        p["rel"] = p.frameId - p.snap
        q = qb[qb.gameId == gid][["playId", "qbId"]]
        qxy = p.merge(q, left_on=["playId", "nflId"], right_on=["playId", "qbId"])[
            ["playId", "frameId", "x", "y"]].rename(columns={"x": "qx", "y": "qy"})
        r = p.merge(rush[rush.gameId == gid][["playId", "nflId"]], on=["playId", "nflId"])
        r = r.merge(qxy, on=["playId", "frameId"], how="left")
        r["dqb"] = np.hypot(r.x - r.qx, r.y - r.qy)
        k = ["playId", "nflId"]
        s0 = r[r.rel == 0].set_index(k)
        s10 = r[r.rel == 10].set_index(k)
        f1 = r[(r.rel >= 1) & (r.rel <= 10)].groupby(k).agg(burst=("s", "max"), a_max_1s=("a", "max"))
        out = f1.join(s0[["dqb"]].rename(columns={"dqb": "dqb_start"}))
        out["getoff"] = np.hypot(s10.x - s0.x, s10.y - s0.y)
        out = out.reset_index().merge(w[["playId", "snap", "fin"]], on="playId")
        out["dur"] = (out.fin - out.snap) / 10
        out["gameId"] = gid
        parts.append(out.drop(columns=["snap", "fin"]))
    T = pd.concat(parts, ignore_index=True)
    T.to_csv(CACHE, index=False)
    print("Tabla rusher-jugada calculada y guardada en caché temporal:", CACHE)

# ------------------------------------------------------------------ marco de modelado
n_rush = rush.groupby(["gameId", "playId"]).size().rename("n_rush").reset_index()
ctx = plays[["gameId", "playId", "down", "yardsToGo", "pff_playAction", "offenseFormation"]]
F = (rush.merge(T, on=["gameId", "playId", "nflId"], how="left")
     .merge(players[["nflId", "displayName", "officialPosition", "weight", "height"]], on="nflId")
     .merge(n_rush, on=["gameId", "playId"]).merge(ctx, on=["gameId", "playId"]))
F["grupo"] = F.officialPosition.map(GRUPO)
F["grupo_alin"] = F.pff_positionLinedUp.map(ALINEACION)

h("1. CONSTRUCCIÓN DE LA MUESTRA (unidad = rusher x jugada)")
print("Filas Pass Rush totales:", len(rush))
steps = [("grupo EDGE/IDL por officialPosition", F.grupo.notna()),
         ("con tracking y snap (burst no nulo)", F.burst.notna()),
         ("duración ventana > 0", F.dur > 0),
         ("posición del QB al snap disponible", F.dqb_start.notna()),
         ("excluye conversiones de 2 pts (down=0)", F.down > 0)]
mask = pd.Series(True, index=F.index)
for name, m in steps:
    mask &= m
    print(f"  {name:45s} -> {int(mask.sum()):>6}")
M = F[mask].copy()
print("Excluidos de otras posiciones (LB/DB en blitz, etc.):", int(F.grupo.isna().sum()))
print("Muestra final:", len(M), "| jugadores:", M.nflId.nunique(), "| partidos:", M.gameId.nunique(),
      "| jugadas:", M.groupby(["gameId", "playId"]).ngroups)
print("Por grupo:", M.groupby("grupo").agg(filas=("pressure", "size"), jugadores=("nflId", "nunique"),
                                           presiones=("pressure", "sum"), tasa=("pressure", "mean")).round(4).to_dict("index"))
snaps_j = M.groupby("nflId").size()
print("Snaps por jugador:", snaps_j.describe().round(1).to_dict())
print("Distribución de snaps: <25:", int((snaps_j < 25).sum()), "| 25-99:", int(((snaps_j >= 25) & (snaps_j < 100)).sum()),
      "| >=100:", int((snaps_j >= 100).sum()), "| % de filas de jugadores con >=100:",
      round(float(M.nflId.map(snaps_j).ge(100).mean() * 100), 1))

print("\nDescriptivos de predictores por grupo:")
print(M.groupby("grupo")[["burst", "a_max_1s", "getoff", "weight", "dqb_start", "dur", "n_rush"]].describe().T.round(2).to_string())

# variables centradas / escaladas
BM, WM, DQ = M.burst.mean(), M.weight.mean(), M.dqb_start.mean()
M["burst_c"] = M.burst - BM                      # yd/s
M["w10"] = (M.weight - WM) / 10                 # por 10 lb
M["idl"] = (M.grupo == "IDL").astype(int)
M["burst_x_idl"] = M.burst_c * M.idl
M["w10_x_idl"] = M.w10 * M.idl
M["dqb_c"] = M.dqb_start - DQ
M["n_rush_c"] = M.n_rush - M.n_rush.mean()
M["third_plus"] = (M.down >= 3).astype(int)
M["ytg_c"] = M.yardsToGo - M.yardsToGo.mean()
M["pa"] = M.pff_playAction
M["shotgun"] = M.offenseFormation.isin(["SHOTGUN", "EMPTY"]).astype(int)
M["dur_c"] = M.dur - M.dur.mean()
pm = M.groupby("nflId").burst.transform("mean")
M["burst_between_c"] = pm - BM
M["burst_within"] = M.burst - pm
M["burst_between_x_idl"] = M.burst_between_c * M.idl
M["burst_within_x_idl"] = M.burst_within * M.idl
print(f"\nCentrado: burst medio={BM:.3f} yd/s | peso medio={WM:.1f} lb | dqb_start medio={DQ:.2f} yd")

CTX = ["dqb_c", "n_rush_c", "third_plus", "ytg_c", "pa", "shotgun"]

h("2. COLINEALIDAD")
print("Correlaciones (rusher-jugada):")
print(M[["burst", "a_max_1s", "getoff", "weight", "idl", "dqb_start", "n_rush", "dur"]].corr().round(3).to_string())
pl_lvl = M.groupby("nflId").agg(burst=("burst", "mean"), weight=("weight", "first"), idl=("idl", "first"))
print("\nCorrelación burst medio vs peso a nivel jugador: todos",
      round(pl_lvl[["burst", "weight"]].corr().iloc[0, 1], 3),
      "| EDGE", round(pl_lvl[pl_lvl.idl == 0][["burst", "weight"]].corr().iloc[0, 1], 3),
      "| IDL", round(pl_lvl[pl_lvl.idl == 1][["burst", "weight"]].corr().iloc[0, 1], 3))
print("VIF modelo principal (sin interacciones):", vif(M, ["burst_c", "w10", "idl"] + CTX))
print("VIF con interacciones (centradas):", vif(M, ["burst_c", "w10", "idl", "burst_x_idl", "w10_x_idl"] + CTX))
print("VIF si se añade a_max_1s y getoff:", vif(M.assign(a1=M.a_max_1s, go=M.getoff), ["burst_c", "a1", "go", "w10", "idl"]))

h("3. MODELOS")
specs = {
    "M0 posición": ["idl"],
    "M1 burst+peso+posición": ["burst_c", "w10", "idl"],
    "M2 +interacción burst×IDL": ["burst_c", "w10", "idl", "burst_x_idl"],
    "M3 +peso×IDL +contexto": ["burst_c", "w10", "idl", "burst_x_idl", "w10_x_idl"] + CTX,
    "M4 burst entre/dentro jugador": ["burst_between_c", "burst_within", "w10", "idl",
                                      "burst_between_x_idl", "burst_within_x_idl", "w10_x_idl"] + CTX,
    "M5 M3 + duración (sensibilidad)": ["burst_c", "w10", "idl", "burst_x_idl", "w10_x_idl"] + CTX + ["dur_c"],
}
mods = {}
for name, cols in specs.items():
    mods[name] = Modelo(M, cols, name)
print(pd.DataFrame([m.resumen() for m in mods.values()]).to_string(index=False))
for name in ["M1 burst+peso+posición", "M2 +interacción burst×IDL", "M3 +peso×IDL +contexto",
             "M4 burst entre/dentro jugador", "M5 M3 + duración (sensibilidad)"]:
    print(f"\n--- {name}  (OR e IC95 con SE robusto por jugador; burst por +1 yd/s, peso por +10 lb)")
    print(mods[name].tabla().round(4).to_string())

h("4. EFECTOS POR GRUPO (combinaciones lineales, SE robusto por jugador)")
for name in ["M2 +interacción burst×IDL", "M3 +peso×IDL +contexto", "M5 M3 + duración (sensibilidad)"]:
    m = mods[name]
    idx = {c: i + 1 for i, c in enumerate(m.cols)}

    def w_(**kw):
        v = np.zeros(m.k)
        for c, val in kw.items():
            v[idx[c]] = val
        return v
    print(f"\n{name}")
    rows = []
    for lab, vec in [("burst EDGE (+1 yd/s)", w_(burst_c=1)),
                     ("burst IDL  (+1 yd/s)", w_(burst_c=1, burst_x_idl=1)),
                     ("interacción burst×IDL", w_(burst_x_idl=1))]:
        est, se, pv = m.lincomb(vec)
        rows.append([lab, math.exp(est), math.exp(est - 1.96 * se), math.exp(est + 1.96 * se), pv])
    if "w10_x_idl" in idx:
        for lab, vec in [("peso EDGE (+10 lb)", w_(w10=1)), ("peso IDL  (+10 lb)", w_(w10=1, w10_x_idl=1)),
                         ("interacción peso×IDL", w_(w10_x_idl=1))]:
            est, se, pv = m.lincomb(vec)
            rows.append([lab, math.exp(est), math.exp(est - 1.96 * se), math.exp(est + 1.96 * se), pv])
    print(pd.DataFrame(rows, columns=["efecto", "OR", "IC95_inf", "IC95_sup", "p"]).round(4).to_string(index=False))
m4 = mods["M4 burst entre/dentro jugador"]
i4 = {c: i + 1 for i, c in enumerate(m4.cols)}
print("\nM4: burst habitual del jugador (entre) vs burst de la jugada respecto a su media (dentro)")
for lab, cols_ in [("entre EDGE", ["burst_between_c"]), ("entre IDL", ["burst_between_c", "burst_between_x_idl"]),
                   ("dentro EDGE", ["burst_within"]), ("dentro IDL", ["burst_within", "burst_within_x_idl"])]:
    v = np.zeros(m4.k)
    for c in cols_:
        v[i4[c]] = 1
    est, se, pv = m4.lincomb(v)
    print(f"  {lab:12s} OR={math.exp(est):.3f} IC95=[{math.exp(est - 1.96 * se):.3f}, {math.exp(est + 1.96 * se):.3f}] p={pv:.4g}")

h("5. BOOTSTRAP POR JUGADOR (M3, 400 réplicas; remuestrea jugadores completos)")
m3cols = specs["M3 +peso×IDL +contexto"]
Xall = np.column_stack([np.ones(len(M))] + [M[c].to_numpy(float) for c in m3cols])
yall = M.pressure.to_numpy(float)
ids = M.nflId.to_numpy()
uniq = np.unique(ids)
pos = {u: np.flatnonzero(ids == u) for u in uniq}
ci3 = {c: i + 1 for i, c in enumerate(m3cols)}
boots = []
for _ in range(400):
    samp = RNG.choice(uniq, size=len(uniq), replace=True)
    rows_ = np.concatenate([pos[u] for u in samp])
    b, _, _ = logit_fit(Xall[rows_], yall[rows_])
    boots.append([b[ci3["burst_c"]], b[ci3["burst_c"]] + b[ci3["burst_x_idl"]], b[ci3["burst_x_idl"]],
                  b[ci3["w10"]], b[ci3["w10"]] + b[ci3["w10_x_idl"]]])
boots = np.exp(np.array(boots))
bt = pd.DataFrame(boots, columns=["OR burst EDGE", "OR burst IDL", "OR interacción", "OR peso EDGE", "OR peso IDL"])
print(bt.quantile([0.025, 0.5, 0.975]).T.round(4).rename(columns={0.025: "p2.5", 0.5: "mediana", 0.975: "p97.5"}).to_string())
print("Proporción de réplicas con OR peso < 1: EDGE", round(float((bt["OR peso EDGE"] < 1).mean()), 3),
      "| IDL", round(float((bt["OR peso IDL"] < 1).mean()), 3))

h("6. CALIDAD DE AJUSTE (M3)")
m3 = mods["M3 +peso×IDL +contexto"]
M["p_hat"] = m3.p
M["dec"] = pd.qcut(M.p_hat, 10, labels=False)
cal = M.groupby("dec").agg(n=("pressure", "size"), esperado=("p_hat", "mean"), observado=("pressure", "mean"))
print("Calibración por deciles de probabilidad predicha:\n", cal.round(4).to_string())
O = M.groupby("dec").pressure.sum()
E = M.groupby("dec").p_hat.sum()
N_ = M.groupby("dec").size()
hl = float(((O - E) ** 2 / (E * (1 - E / N_))).sum())
print(f"Hosmer-Lemeshow (10 grupos): chi2={hl:.2f}, gl=8 (referencia crítica 5% = 15.51). "
      "Nota: con datos agrupados por jugador el test es aproximado.")
for g_ in ["EDGE", "IDL"]:
    s = M.grupo == g_
    print(f"AUC dentro de {g_}: {auc(M.pressure[s].to_numpy(), M.p_hat[s].to_numpy()):.4f}")
# validación cruzada por jugador (5 folds) para medir optimismo
folds = pd.Series(RNG.integers(0, 5, len(uniq)), index=uniq)
M["fold"] = M.nflId.map(folds)
oos = np.zeros(len(M))
for f in range(5):
    tr, te = (M.fold != f).to_numpy(), (M.fold == f).to_numpy()
    b, _, _ = logit_fit(Xall[tr], yall[tr])
    oos[te] = 1 / (1 + np.exp(-(Xall[te] @ b)))
print(f"AUC fuera de muestra (5-fold por jugador): {auc(yall, oos):.4f} | in-sample: {auc(yall, m3.p):.4f}")
print(f"Brier fuera de muestra: {np.mean((yall - oos) ** 2):.5f} | Brier tasa base: {np.mean((yall - yall.mean()) ** 2):.5f}")

h("7. SENSIBILIDAD AL UMBRAL MÍNIMO DE SNAPS Y A LA DEFINICIÓN DE POSICIÓN")
rows = []
for thr in [1, 25, 50, 100, 150, 200]:
    keep = M.nflId.map(snaps_j) >= thr
    sub = M[keep]
    m = Modelo(sub, m3cols, f">={thr}")
    ix = {c: i + 1 for i, c in enumerate(m3cols)}

    def lc(cols_):
        v = np.zeros(m.k)
        for c in cols_:
            v[ix[c]] = 1
        e_, s_, p_ = m.lincomb(v)
        return math.exp(e_), math.exp(e_ - 1.96 * s_), math.exp(e_ + 1.96 * s_), p_
    be, bi, we, wi = lc(["burst_c"]), lc(["burst_c", "burst_x_idl"]), lc(["w10"]), lc(["w10", "w10_x_idl"])
    rows.append({"umbral": thr, "filas": len(sub), "jugadores": sub.nflId.nunique(),
                 "OR_burst_EDGE": be[0], "IC_EDGE": f"[{be[1]:.2f},{be[2]:.2f}]",
                 "OR_burst_IDL": bi[0], "IC_IDL": f"[{bi[1]:.2f},{bi[2]:.2f}]",
                 "OR_peso_EDGE": we[0], "p_peso_EDGE": we[3], "OR_peso_IDL": wi[0], "p_peso_IDL": wi[3]})
print(pd.DataFrame(rows).round(4).to_string(index=False))

A = M[M.grupo_alin.notna()].copy()
A["idl"] = (A.grupo_alin == "IDL").astype(int)
A["burst_x_idl"] = A.burst_c * A.idl
A["w10_x_idl"] = A.w10 * A.idl
ma = Modelo(A, m3cols, "M3 con grupo por alineación")
print("\nGrupo definido por pff_positionLinedUp (alineación real en la jugada):", ma.resumen())
ix = {c: i + 1 for i, c in enumerate(m3cols)}
for lab, cols_ in [("burst EDGE", ["burst_c"]), ("burst IDL", ["burst_c", "burst_x_idl"]),
                   ("peso EDGE", ["w10"]), ("peso IDL", ["w10", "w10_x_idl"])]:
    v = np.zeros(ma.k)
    for c in cols_:
        v[ix[c]] = 1
    e_, s_, p_ = ma.lincomb(v)
    print(f"  {lab:10s} OR={math.exp(e_):.3f} IC95=[{math.exp(e_ - 1.96 * s_):.3f}, {math.exp(e_ + 1.96 * s_):.3f}] p={p_:.4g}")
print("Coincidencia officialPosition vs alineación:\n",
      pd.crosstab(M.grupo, M.grupo_alin.fillna("otra")).to_string())

# métrica alternativa de explosividad
for alt in ["a_max_1s", "getoff"]:
    sub = M.dropna(subset=[alt]).copy()
    sub["alt_c"] = sub[alt] - sub[alt].mean()
    sub["alt_x_idl"] = sub.alt_c * sub.idl
    sd = sub[alt].std()
    m = Modelo(sub, ["alt_c", "w10", "idl", "alt_x_idl", "w10_x_idl"] + CTX, alt)
    e_, s_, p_ = m.lincomb(np.r_[0, 1, np.zeros(m.k - 2)])
    print(f"Alternativa {alt}: OR EDGE por +1 DE ({sd:.2f}) = {math.exp(e_ * sd):.3f} p={p_:.3g} | AUC={m.resumen()['AUC']}")
sd_b = M.burst.std()
e_, s_, p_ = m3.lincomb(np.r_[0, 1, np.zeros(m3.k - 2)])
print(f"Referencia burst: OR EDGE por +1 DE ({sd_b:.2f}) = {math.exp(e_ * sd_b):.3f} | AUC M3={m3.resumen()['AUC']}")

h("8. CURVAS DE PROBABILIDAD PREDICHA (M3; contexto en su media, peso medio del grupo)")
ctx_mean = M[CTX].mean()
rows = []
for g_, idl in [("EDGE", 0), ("IDL", 1)]:
    sub = M[M.grupo == g_]
    wg = (sub.weight.mean() - WM) / 10
    for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
        bv = sub.burst.quantile(q)
        x = {"burst_c": bv - BM, "w10": wg, "idl": idl, "burst_x_idl": (bv - BM) * idl, "w10_x_idl": wg * idl,
             **ctx_mean.to_dict()}
        eta = m3.b[0] + sum(m3.b[i + 1] * x[c] for i, c in enumerate(m3cols))
        rows.append({"grupo": g_, "percentil_burst": int(q * 100), "burst": round(bv, 2),
                     "prob_predicha": round(1 / (1 + math.exp(-eta)), 4)})
print(pd.DataFrame(rows).to_string(index=False))
print("\nTasa observada por decil de burst dentro de cada grupo (IC95 Wilson):")
for g_ in ["EDGE", "IDL"]:
    sub = M[M.grupo == g_].copy()
    sub["d"] = pd.qcut(sub.burst, 10, labels=False)
    t = sub.groupby("d").agg(burst_lo=("burst", "min"), burst_hi=("burst", "max"), n=("pressure", "size"),
                             k=("pressure", "sum"))
    t["tasa"] = t.k / t.n
    lo, hi = wilson(t.k, t.n)
    t["IC_inf"], t["IC_sup"] = lo, hi
    print(f"\n{g_}\n", t.round(3).to_string())

h("9. JUGADORES POR ENCIMA DE LO ESPERADO (M3)")
P = M.groupby("nflId").agg(nombre=("displayName", "first"), pos=("officialPosition", "first"),
                           grupo=("grupo", "first"), peso=("weight", "first"), snaps=("pressure", "size"),
                           presiones=("pressure", "sum"), esperadas=("p_hat", "sum"),
                           var=("p_hat", lambda v: float(np.sum(v * (1 - v)))), burst_med=("burst", "median"))
P["tasa_obs"] = P.presiones / P.snaps
P["tasa_esp"] = P.esperadas / P.snaps
P["O_E"] = P.presiones / P.esperadas
P["dif_x100"] = (P.tasa_obs - P.tasa_esp) * 100
P["z"] = (P.presiones - P.esperadas) / np.sqrt(P["var"])
lo, hi = wilson(P.presiones, P.snaps)
P["IC_obs_inf"], P["IC_obs_sup"] = lo, hi
big = P[P.snaps >= 100]
phi = float(np.mean(big.z ** 2))
print(f"Sobredispersión entre jugadores (media de z² en jugadores >=100 snaps; 1 = sin efecto jugador): {phi:.2f}")
P["z_aj"] = P.z / math.sqrt(max(phi, 1))
P["p_aj"] = 2 * (1 - ncdf(np.abs(P.z_aj)))
cols = ["nombre", "pos", "peso", "snaps", "presiones", "tasa_obs", "IC_obs_inf", "IC_obs_sup", "tasa_esp",
        "dif_x100", "O_E", "z_aj", "p_aj", "burst_med"]
for g_ in ["EDGE", "IDL"]:
    s = P[(P.snaps >= 100) & (P.grupo == g_)].sort_values("z_aj", ascending=False)
    print(f"\n{g_}: top 12 por z ajustado (>=100 snaps)\n", s[cols].head(12).round(3).to_string(index=False))
    print(f"{g_}: bottom 5\n", s[cols].tail(5).round(3).to_string(index=False))
print("\nJugadores >=100 snaps con z_aj > 1.96:", int(((P.snaps >= 100) & (P.z_aj > 1.96)).sum()),
      "| < -1.96:", int(((P.snaps >= 100) & (P.z_aj < -1.96)).sum()), "de", int((P.snaps >= 100).sum()))
print("Esperado por azar con 5% bilateral:", round(0.05 * (P.snaps >= 100).sum(), 1))
mid = P[(P.snaps >= 50) & (P.snaps < 100)].sort_values("z_aj", ascending=False)
print("\nEn observación (50-99 snaps, z_aj > 1.5):\n", mid[mid.z_aj > 1.5][cols].round(3).to_string(index=False))
h("10. CONFUSOR: RUSHERS SIN BLOQUEADOR ASIGNADO")
bl = pff[pff.pff_nflIdBlockedPlayer.notna()].groupby(
    ["gameId", "playId", "pff_nflIdBlockedPlayer"]).size().rename("n_blockers").reset_index().rename(
    columns={"pff_nflIdBlockedPlayer": "nflId"})
bl["nflId"] = bl.nflId.astype(int)
M = M.merge(bl, on=["gameId", "playId", "nflId"], how="left")
M["n_blockers"] = M.n_blockers.fillna(0)
M["unblocked"] = (M.n_blockers == 0).astype(int)
M["double"] = (M.n_blockers >= 2).astype(int)
print(M.groupby("unblocked").agg(n=("pressure", "size"), tasa=("pressure", "mean"), burst=("burst", "mean")).round(3).to_string())
print(M.groupby("double").agg(n=("pressure", "size"), tasa=("pressure", "mean"), burst=("burst", "mean")).round(3).to_string())
for name, sub, extra in [("M3 solo rushers bloqueados", M[M.unblocked == 0], []),
                         ("M3 + indicadores sin bloqueo / doble", M, ["unblocked", "double"])]:
    m = Modelo(sub, m3cols + extra, name)
    ix = {c: i + 1 for i, c in enumerate(m.cols)}
    print(f"\n{name}: n={m.n}, AUC={m.resumen()['AUC']}")
    for lab, cols_ in [("burst EDGE", ["burst_c"]), ("burst IDL", ["burst_c", "burst_x_idl"]),
                       ("interacción", ["burst_x_idl"]), ("peso EDGE", ["w10"]), ("peso IDL", ["w10", "w10_x_idl"])] + \
            [(c, [c]) for c in extra]:
        v = np.zeros(m.k)
        for c in cols_:
            v[ix[c]] = 1
        e_, s_, p_ = m.lincomb(v)
        print(f"  {lab:12s} OR={math.exp(e_):.3f} IC95=[{math.exp(e_ - 1.96 * s_):.3f}, {math.exp(e_ + 1.96 * s_):.3f}] p={p_:.4g}")

h("11. EFECTO DE BURST POR +1 DESVIACIÓN ESTÁNDAR DENTRO DEL GRUPO (M3)")
ix = {c: i + 1 for i, c in enumerate(m3cols)}
for g_, cols_ in [("EDGE", ["burst_c"]), ("IDL", ["burst_c", "burst_x_idl"])]:
    sd = M[M.grupo == g_].burst.std()
    v = np.zeros(m3.k)
    for c in cols_:
        v[ix[c]] = sd
    e_, s_, p_ = m3.lincomb(v)
    print(f"  {g_}: DE={sd:.2f} yd/s -> OR={math.exp(e_):.3f} IC95=[{math.exp(e_ - 1.96 * s_):.3f}, {math.exp(e_ + 1.96 * s_):.3f}]")
print("\nFIN", flush=True)
