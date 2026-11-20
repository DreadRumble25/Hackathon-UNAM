"""Motor de datos de NFL Matchup Analytics.

Lee los CSV de data/ (solo lectura), procesa el tracking archivo por archivo y
construye en memoria las tablas derivadas y el modelo logístico. No escribe nada
en disco: todo se recalcula al arrancar el servidor.

Unidades de análisis:
  - rusher x jugada  (pff_role == "Pass Rush")
  - bloqueador x jugada (pff_role == "Pass Block")
Nunca se usa el frame como observación.
"""
from __future__ import annotations

import glob
import math
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent

SNAP = {"ball_snap", "autoevent_ballsnap"}
FIN = {"pass_forward", "autoevent_passforward", "qb_sack", "qb_strip_sack", "run",
       "pass_tipped", "fumble", "autoevent_passinterrupted"}
RUSH_GROUP = {"DE": "EDGE", "OLB": "EDGE", "DT": "IDL", "NT": "IDL"}
BLOCK_GROUP = {"T": "OT", "G": "IOL", "C": "IOL"}
RUSH_GROUPS = ("EDGE", "IDL")
BLOCK_GROUPS = ("OT", "IOL")
CTX = ["dqb_c", "n_rush_c", "third_plus", "ytg_c", "pa", "shotgun"]
TERM_LABELS = {
    "burst_c": "Burst (+1 yd/s, EDGE)",
    "w10": "Peso (+10 lb, EDGE)",
    "idl": "Grupo IDL vs EDGE",
    "burst_x_idl": "Interacción burst × IDL",
    "w10_x_idl": "Interacción peso × IDL",
    "dqb_c": "Distancia al QB en el snap (+1 yd)",
    "n_rush_c": "Rushers en la jugada (+1)",
    "third_plus": "3.er o 4.º down",
    "ytg_c": "Yardas por avanzar (+1)",
    "pa": "Play action",
    "shotgun": "Shotgun / Empty",
}
PHYS = [
    ("burst", "Explosividad inicial (burst)", "yd/s", "Velocidad máxima en el primer segundo tras el snap"),
    ("getoff", "Desplazamiento 1er segundo (getoff)", "yd", "Distancia en línea recta entre el snap y el frame 10"),
    ("a_max_1s", "Aceleración máx. 1er segundo", "yd/s²", "Máximo de a en el primer segundo"),
    ("s_max", "Velocidad máxima", "yd/s", "Máximo de s entre el snap y el pase/sack"),
    ("s_mean", "Velocidad promedio", "yd/s", "Promedio de s entre el snap y el pase/sack"),
    ("a_max", "Aceleración máxima", "yd/s²", "Máximo de a entre el snap y el pase/sack"),
    ("a_mean", "Aceleración promedio", "yd/s²", "Promedio de a entre el snap y el pase/sack"),
    ("dist", "Distancia recorrida", "yd", "Suma de desplazamientos entre frames consecutivos, snap a pase/sack"),
]
PHYS_KEYS = [k for k, *_ in PHYS]


# ======================================================================== utilidades
def ncdf(z):
    z = np.asarray(z, dtype=float)
    return 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))


def wilson(k, n, z=1.96):
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = k / n
        c = (p + z * z / (2 * n)) / (1 + z * z / n)
        hw = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - hw, c + hw


def logistic(x):
    return 1 / (1 + np.exp(-x))


def logit_fit(X, y, max_iter=60, tol=1e-10):
    b = np.zeros(X.shape[1])
    for _ in range(max_iter):
        p = logistic(X @ b)
        H = X.T @ ((p * (1 - p))[:, None] * X)
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < tol:
            break
    p = logistic(X @ b)
    H = X.T @ ((p * (1 - p))[:, None] * X)
    return b, p, np.linalg.inv(H)


def cluster_vcov(X, y, p, bread, groups):
    u = X * (y - p)[:, None]
    gs = pd.DataFrame(u).groupby(groups).sum().to_numpy()
    G, (N, K) = gs.shape[0], X.shape
    c = G / (G - 1) * (N - 1) / (N - K)
    return c * bread @ (gs.T @ gs) @ bread


def auc(y, p):
    r = pd.Series(p).rank().to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def corr_test(x, y):
    m = pd.notna(x) & pd.notna(y)
    x = pd.Series(x)[m].astype(float)
    y = pd.Series(y)[m].astype(float)
    n = len(x)
    if n < 10:
        return {"n": n, "pearson": None, "p_pearson": None, "spearman": None, "p_spearman": None}
    out = {"n": n}
    for name, a, b in [("pearson", x, y), ("spearman", x.rank(), y.rank())]:
        r = float(np.corrcoef(a, b)[0, 1])
        z = math.atanh(min(max(r, -0.999999), 0.999999)) * math.sqrt(n - 3)
        out[name] = r
        out["p_" + name] = float(2 * (1 - ncdf(abs(z))))
    return out


def clean(o):
    """Convierte numpy/pandas a tipos JSON y NaN/inf a None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if o is pd.NA or o is pd.NaT:
        return None
    return o


def records(df: pd.DataFrame):
    return clean(df.to_dict("records"))


def pct_rank(values, v):
    values = np.asarray([x for x in values if x is not None and not np.isnan(x)], dtype=float)
    if v is None or len(values) == 0 or np.isnan(v):
        return None
    return float(((values < v).mean() + 0.5 * (values == v).mean()) * 100)


class Logit:
    def __init__(self, X: pd.DataFrame, y: np.ndarray, clusters: np.ndarray):
        self.cols = list(X.columns)
        A = np.column_stack([np.ones(len(X)), X.to_numpy(float)])
        self.b, self.p, bread = logit_fit(A, y)
        self.V = cluster_vcov(A, y, self.p, bread, clusters)
        self.k = A.shape[1]
        self.n = len(y)
        self.G = len(np.unique(clusters))
        self.ll = float(np.sum(y * np.log(self.p) + (1 - y) * np.log(1 - self.p)))
        p0 = y.mean()
        self.ll0 = float(len(y) * (p0 * np.log(p0) + (1 - p0) * np.log(1 - p0)))
        self.auc = auc(y, self.p)
        self.brier = float(np.mean((y - self.p) ** 2))
        self.brier0 = float(np.mean((y - p0) ** 2))

    def idx(self, c):
        return self.cols.index(c) + 1

    def lincomb(self, weights: dict):
        w = np.zeros(self.k)
        for c, v in weights.items():
            w[0 if c == "(intercepto)" else self.idx(c)] = v
        est = float(w @ self.b)
        se = math.sqrt(float(w @ self.V @ w))
        p = float(2 * (1 - ncdf(abs(est / se)))) if se > 0 else None
        return {"OR": math.exp(est), "lo": math.exp(est - 1.96 * se), "hi": math.exp(est + 1.96 * se),
                "p": p, "coef": est, "se": se}

    def predict_row(self, xdict: dict):
        w = np.zeros(self.k)
        w[0] = 1
        for c, v in xdict.items():
            w[self.idx(c)] = v
        eta = float(w @ self.b)
        se = math.sqrt(float(w @ self.V @ w))
        return logistic(eta), logistic(eta - 1.96 * se), logistic(eta + 1.96 * se)


# ======================================================================== motor
class Engine:
    def __init__(self):
        self.ready = False
        self.error: str | None = None
        self.stage = "en espera"
        self.progress = 0.0
        self.t0 = None
        self.t_build = None
        self._lock = threading.Lock()

    # --------------------------------------------------------------- arranque
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self.t0 = time.time()
        try:
            self._build()
            self.ready = True
            self.stage = "listo"
            self.progress = 1.0
            self.t_build = time.time() - self.t0
        except Exception as exc:  # pragma: no cover - se informa por /api/estado
            self.error = f"{type(exc).__name__}: {exc}"
            self.stage = "error"
            traceback.print_exc()

    def status(self):
        return {"listo": self.ready, "etapa": self.stage, "progreso": round(self.progress, 3),
                "error": self.error, "segundos": round(time.time() - self.t0, 1) if self.t0 else None}

    # --------------------------------------------------------------- tracking
    def _tracking(self, D: Path, qb: pd.DataFrame):
        files = sorted(glob.glob(str(D / "tracking" / "tracking_*.csv")))
        if not files:
            raise FileNotFoundError("No hay archivos tracking_*.csv en data/")
        parts, wins = [], []
        k = ["playId", "nflId"]
        for i, t in enumerate(files):
            df = pd.read_csv(t, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "s", "a", "event"])
            gid = int(df.gameId.iloc[0])
            ev = df[df.event.notna()]
            w = pd.concat([ev[ev.event.isin(SNAP)].groupby("playId").frameId.min().rename("snap"),
                           ev[ev.event.isin(FIN)].groupby("playId").frameId.min().rename("fin"),
                           df.groupby("playId").frameId.max().rename("last")], axis=1)
            w["fin"] = w.fin.fillna(w["last"])
            w = w.dropna(subset=["snap"]).reset_index()
            w["gameId"] = gid
            wins.append(w[["gameId", "playId", "snap", "fin"]])

            p = df[df.nflId.notna()].drop(columns=["event"]).merge(w[["playId", "snap", "fin"]], on="playId")
            p["nflId"] = p.nflId.astype(int)
            p["rel"] = p.frameId - p.snap
            p = p[p.rel >= 0].sort_values(["playId", "nflId", "frameId"])
            g = p.groupby(k)
            cont = g.frameId.diff() == 1
            p["step"] = np.where(cont, np.hypot(g.x.diff(), g.y.diff()), 0.0)
            win = p[p.frameId <= p.fin]
            agg = win.groupby(k).agg(frames=("frameId", "size"), s_max=("s", "max"), s_mean=("s", "mean"),
                                     a_max=("a", "max"), a_mean=("a", "mean"), dist=("step", "sum"))
            v1 = win[win.rel <= 10].groupby(k).s.max().rename("burst_v1")
            f1 = p[(p.rel >= 1) & (p.rel <= 10)].groupby(k).agg(burst=("s", "max"), a_max_1s=("a", "max"))
            s0 = p[p.rel == 0].set_index(k)[["x", "y"]]
            s10 = p[p.rel == 10].set_index(k)[["x", "y"]]
            getoff = np.hypot(s10.x - s0.x, s10.y - s0.y).rename("getoff")
            s0r = s0.reset_index()
            qpos = s0r.merge(qb[qb.gameId == gid][["playId", "qbId"]], left_on=["playId", "nflId"],
                             right_on=["playId", "qbId"])[["playId", "x", "y"]].rename(columns={"x": "qx", "y": "qy"})
            s0r = s0r.merge(qpos, on="playId", how="left")
            s0r["dqb_start"] = np.hypot(s0r.x - s0r.qx, s0r.y - s0r.qy)
            out = agg.join(v1).join(f1).join(getoff).join(s0r.set_index(k)[["dqb_start"]]).reset_index()
            out["gameId"] = gid
            parts.append(out)
            self.progress = 0.05 + 0.75 * (i + 1) / len(files)
            self.stage = f"procesando tracking ({i + 1}/{len(files)})"
        return pd.concat(parts, ignore_index=True), pd.concat(wins, ignore_index=True)

    # --------------------------------------------------------------- construcción
    def _build(self):
        self.stage = "leyendo archivos"
        hits = sorted(RAIZ.glob("data/**/games.csv"))
        if not hits:
            raise FileNotFoundError("No se encontró games.csv dentro de data/")
        D = hits[0].parent
        games = pd.read_csv(D / "games.csv")
        plays = pd.read_csv(D / "plays.csv")
        players = pd.read_csv(D / "players.csv")
        pff = pd.read_csv(D / "pffScoutingData.csv")
        self.progress = 0.05

        ht = players.height.str.split("-", expand=True).astype(float)
        players["height_in"] = ht[0] * 12 + ht[1]
        plays = plays.merge(games[["gameId", "week", "homeTeamAbbr", "visitorTeamAbbr", "gameDate"]], on="gameId")
        qb = pff[pff.pff_role == "Pass"][["gameId", "playId", "nflId"]].rename(columns={"nflId": "qbId"})

        phys, win = self._tracking(D, qb)
        win["dur"] = (win.fin - win.snap) / 10
        self.stage = "construyendo tablas"

        pcols = ["gameId", "playId", "week", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
                 "pff_playAction", "offenseFormation", "quarter", "pff_passCoverageType", "passResult"]
        base = (pff.merge(plays[pcols], on=["gameId", "playId"])
                .merge(win[["gameId", "playId", "dur"]], on=["gameId", "playId"], how="left")
                .merge(phys, on=["gameId", "playId", "nflId"], how="left")
                .merge(players[["nflId", "displayName", "officialPosition", "weight", "height_in"]], on="nflId"))
        defensive = base.pff_role.isin(["Pass Rush", "Coverage"])
        base["team"] = np.where(defensive, base.defensiveTeam, base.possessionTeam)
        base["opp"] = np.where(defensive, base.possessionTeam, base.defensiveTeam)

        # presión por jugada (cualquier defensor), para "presión permitida" del equipo ofensivo
        anyp = pff.assign(pp=pff[["pff_hit", "pff_hurry", "pff_sack"]].fillna(0).max(axis=1)).groupby(
            ["gameId", "playId"]).pp.max().rename("pressured").reset_index()
        PL = plays[["gameId", "playId", "week", "possessionTeam", "defensiveTeam", "down"]].merge(anyp, on=["gameId", "playId"])

        # bloqueadores asignados a cada defensor
        nb = pff[pff.pff_nflIdBlockedPlayer.notna()].groupby(["gameId", "playId", "pff_nflIdBlockedPlayer"]).size()
        nb = nb.rename("n_blockers").reset_index().rename(columns={"pff_nflIdBlockedPlayer": "nflId"})
        nb["nflId"] = nb.nflId.astype(int)
        nrush = pff[pff.pff_role == "Pass Rush"].groupby(["gameId", "playId"]).size().rename("n_rush").reset_index()

        # ---------------- rushers
        R = base[base.pff_role == "Pass Rush"].copy()
        for c in ["pff_hit", "pff_hurry", "pff_sack"]:
            R[c] = R[c].fillna(0).astype(int)
        R["pressure"] = R[["pff_hit", "pff_hurry", "pff_sack"]].max(axis=1)
        R["grupo"] = R.officialPosition.map(RUSH_GROUP).fillna("OTRO")
        R = R.merge(nb, on=["gameId", "playId", "nflId"], how="left").merge(nrush, on=["gameId", "playId"], how="left")
        R["n_blockers"] = R.n_blockers.fillna(0).astype(int)
        R["modelable"] = (R.grupo.isin(RUSH_GROUPS) & R.burst.notna() & (R.dur > 0) & R.dqb_start.notna()
                          & (R.down > 0))
        R = R.reset_index(drop=True)

        # ---------------- bloqueadores
        B = base[base.pff_role == "Pass Block"].copy()
        for c in ["pff_beatenByDefender", "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]:
            B[c] = B[c].fillna(0).astype(int)
        B["allowed"] = B[["pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed"]].max(axis=1)
        B["lost"] = B[["allowed", "pff_beatenByDefender"]].max(axis=1)
        B["grupo"] = B.officialPosition.map(BLOCK_GROUP).fillna("OTRO")
        B["defId"] = B.pff_nflIdBlockedPlayer.astype("Int64")
        dinfo = base[["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp", "displayName", "officialPosition",
                      "weight", "burst"]].rename(columns={"nflId": "defId", "pff_role": "def_role",
                                                          "pff_positionLinedUp": "def_lined", "displayName": "def_name",
                                                          "officialPosition": "def_pos", "weight": "def_weight",
                                                          "burst": "def_burst"})
        dinfo["defId"] = dinfo.defId.astype("Int64")
        B = B.merge(dinfo, on=["gameId", "playId", "defId"], how="left")
        B["def_grupo"] = np.where(B.defId.isna(), None, B.def_pos.map(RUSH_GROUP).fillna("OTRO"))
        B = B.reset_index(drop=True)

        self.progress = 0.85
        self.stage = "ajustando modelo"
        self.games, self.plays, self.players, self.PL = games, plays, players, PL
        self.R, self.B, self.base = R, B, base
        self._fit_models()
        self.progress = 0.93
        self.stage = "calculando resúmenes"
        self._priors()
        self._player_tables()
        self._lab()
        self.progress = 0.99

    # --------------------------------------------------------------- modelo
    def _design(self, df: pd.DataFrame, var="burst"):
        c = self.cst
        X = pd.DataFrame(index=df.index)
        X["burst_c"] = df[var] - c[var]
        X["w10"] = (df.weight - c["weight"]) / 10
        X["idl"] = (df.grupo == "IDL").astype(int)
        X["burst_x_idl"] = X.burst_c * X.idl
        X["w10_x_idl"] = X.w10 * X.idl
        X["dqb_c"] = df.dqb_start - c["dqb"]
        X["n_rush_c"] = df.n_rush - c["n_rush"]
        X["third_plus"] = (df.down >= 3).astype(int)
        X["ytg_c"] = df.yardsToGo - c["ytg"]
        X["pa"] = df.pff_playAction.astype(int)
        X["shotgun"] = df.offenseFormation.isin(["SHOTGUN", "EMPTY"]).astype(int)
        return X

    def _fit_models(self):
        R = self.R
        M = R[R.modelable].copy()
        self.cst = {"burst": M.burst.mean(), "getoff": M.getoff.mean(), "a_max_1s": M.a_max_1s.mean(),
                    "weight": M.weight.mean(), "dqb": M.dqb_start.mean(), "n_rush": M.n_rush.mean(),
                    "ytg": M.yardsToGo.mean()}
        X = self._design(M)
        y = M.pressure.to_numpy(float)
        cl = M.nflId.to_numpy()
        self.m3 = Logit(X, y, cl)
        self.X3 = X
        R["p_hat"] = np.nan
        R.loc[M.index, "p_hat"] = self.m3.p
        R["eta"] = np.nan
        R.loc[M.index, "eta"] = np.log(self.m3.p / (1 - self.m3.p))
        self.Mpop = R[R.modelable]

        # M4: entre / dentro del jugador
        pm = M.groupby("nflId").burst.transform("mean")
        X4 = X.drop(columns=["burst_c", "burst_x_idl"]).copy()
        X4.insert(0, "between", pm - self.cst["burst"])
        X4.insert(1, "within", M.burst - pm)
        X4["between_x_idl"] = X4.between * X4.idl
        X4["within_x_idl"] = X4.within * X4.idl
        self.m4 = Logit(X4, y, cl)

        # métricas alternativas
        self.alt = {}
        for var in ["burst", "getoff", "a_max_1s"]:
            sub = M.dropna(subset=[var])
            mod = self.m3 if var == "burst" else Logit(self._design(sub, var), sub.pressure.to_numpy(float),
                                                       sub.nflId.to_numpy())
            self.alt[var] = (mod, sub)

        # robustez
        snaps = M.groupby("nflId").size()
        self.robust = []
        for label, sub in [("Modelo principal", M),
                           ("Solo rushers con bloqueador asignado", M[M.n_blockers > 0]),
                           ("Jugadores con ≥50 oportunidades", M[M.nflId.map(snaps) >= 50]),
                           ("Jugadores con ≥100 oportunidades", M[M.nflId.map(snaps) >= 100]),
                           ("Jugadores con ≥150 oportunidades", M[M.nflId.map(snaps) >= 150])]:
            mod = self.m3 if label == "Modelo principal" else Logit(self._design(sub), sub.pressure.to_numpy(float),
                                                                    sub.nflId.to_numpy())
            e = mod.lincomb({"burst_c": 1})
            i_ = mod.lincomb({"burst_c": 1, "burst_x_idl": 1})
            w_ = mod.lincomb({"w10": 1})
            self.robust.append({"analisis": label, "n": mod.n, "jugadores": mod.G,
                                "or_edge": e["OR"], "lo_edge": e["lo"], "hi_edge": e["hi"],
                                "or_idl": i_["OR"], "lo_idl": i_["lo"], "hi_idl": i_["hi"],
                                "or_peso": w_["OR"], "p_peso": w_["p"]})

        # sobredispersión para z ajustado
        P = M.assign(v=self.m3.p * (1 - self.m3.p), ph=self.m3.p).groupby("nflId").agg(
            n=("pressure", "size"), k=("pressure", "sum"), e=("ph", "sum"), v=("v", "sum"))
        big = P[P.n >= 100]
        self.phi = max(float(np.mean(((big.k - big.e) / np.sqrt(big.v)) ** 2)), 1.0)

    # --------------------------------------------------------------- priors de shrinkage
    @staticmethod
    def _prior(k, n):
        mu = k.sum() / n.sum()
        p = k / n
        var_obs = np.average((p - mu) ** 2, weights=n)
        var_bin = np.average(mu * (1 - mu) / n, weights=n)
        var_true = max(var_obs - var_bin, 1e-6)
        m = max(mu * (1 - mu) / var_true - 1, 1.0)
        return float(mu), float(min(m, 2000.0))

    def _priors(self):
        self.prior_r, self.prior_b = {}, {}
        r = self.R.groupby(["grupo", "nflId"]).agg(k=("pressure", "sum"), n=("pressure", "size")).reset_index()
        for g, sub in r.groupby("grupo"):
            s = sub[sub.n >= 100]
            if len(s) < 5:
                s = sub[sub.n >= 20]
            self.prior_r[g] = self._prior(s.k, s.n) if len(s) >= 5 else (float(sub.k.sum() / sub.n.sum()), 100.0)
        b = self.B.groupby(["grupo", "nflId"]).agg(k=("lost", "sum"), n=("lost", "size")).reset_index()
        b["k"] = b.n - b.k  # bloqueos efectivos
        for g, sub in b.groupby("grupo"):
            s = sub[sub.n >= 100]
            if len(s) < 5:
                s = sub[sub.n >= 20]
            self.prior_b[g] = self._prior(s.k, s.n) if len(s) >= 5 else (float(sub.k.sum() / sub.n.sum()), 100.0)

    # --------------------------------------------------------------- agregados
    def agg_rushers(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        d = df.assign(v=df.p_hat * (1 - df.p_hat), mp=df.pressure.where(df.modelable))
        a = d.groupby("nflId").agg(nombre=("displayName", "first"), pos=("officialPosition", "first"),
                                   grupo=("grupo", "first"), equipo=("team", lambda s: "/".join(sorted(set(s)))),
                                   peso=("weight", "first"), altura=("height_in", "first"),
                                   snaps=("pressure", "size"), hurries=("pff_hurry", "sum"), hits=("pff_hit", "sum"),
                                   sacks=("pff_sack", "sum"), presiones=("pressure", "sum"),
                                   n_model=("modelable", "sum"), k_model=("mp", "sum"), esperadas=("p_hat", "sum"),
                                   var=("v", "sum"), burst_med=("burst", "median"), getoff_med=("getoff", "median"))
        a = a.reset_index()
        a["tasa"] = a.presiones / a.snaps
        lo, hi = wilson(a.presiones, a.snaps)
        a["ic_lo"], a["ic_hi"] = lo, hi
        a["tasa_esp"] = np.where(a.n_model > 0, a.esperadas / a.n_model.replace(0, np.nan), np.nan)
        a["tasa_model_obs"] = np.where(a.n_model > 0, a.k_model / a.n_model.replace(0, np.nan), np.nan)
        a["o_e"] = a.k_model / a.esperadas.replace(0, np.nan)
        a["z_aj"] = (a.k_model - a.esperadas) / np.sqrt(a["var"].replace(0, np.nan)) / math.sqrt(self.phi)
        a["p_aj"] = 2 * (1 - ncdf(np.abs(a.z_aj.fillna(0))))
        a.loc[a.z_aj.isna(), "p_aj"] = np.nan
        mu = a.grupo.map(lambda g: self.prior_r.get(g, (np.nan, 100))[0])
        m = a.grupo.map(lambda g: self.prior_r.get(g, (np.nan, 100))[1])
        a["tasa_ajustada"] = (a.presiones + m * mu) / (a.snaps + m)
        return a

    def agg_blockers(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        a = df.groupby("nflId").agg(nombre=("displayName", "first"), pos=("officialPosition", "first"),
                                    grupo=("grupo", "first"), equipo=("team", lambda s: "/".join(sorted(set(s)))),
                                    peso=("weight", "first"), altura=("height_in", "first"),
                                    snaps=("lost", "size"), permitidas=("allowed", "sum"),
                                    superado=("pff_beatenByDefender", "sum"), perdidos=("lost", "sum"),
                                    sacks_perm=("pff_sackAllowed", "sum")).reset_index()
        a["efectividad"] = 1 - a.perdidos / a.snaps
        lo, hi = wilson(a.snaps - a.perdidos, a.snaps)
        a["ic_lo"], a["ic_hi"] = lo, hi
        a["tasa_permitida"] = a.permitidas / a.snaps
        mu = a.grupo.map(lambda g: self.prior_b.get(g, (np.nan, 100))[0])
        m = a.grupo.map(lambda g: self.prior_b.get(g, (np.nan, 100))[1])
        a["efectividad_ajustada"] = (a.snaps - a.perdidos + m * mu) / (a.snaps + m)
        return a

    def _player_tables(self):
        base = self.base
        self.rush_season = self.agg_rushers(self.R)
        self.block_season = self.agg_blockers(self.B)
        # física por jugador y rol (mediana por jugada)
        ph = base[base.frames.notna()].groupby(["nflId", "pff_role"])
        self.phys_player = ph[PHYS_KEYS].median()
        self.phys_player["n"] = ph.size()
        self.phys_player = self.phys_player.reset_index().merge(
            self.players[["nflId", "officialPosition"]], on="nflId")
        # info general
        role_n = base.groupby(["nflId", "pff_role"]).size().unstack(fill_value=0)
        lined = base.groupby(["nflId", "pff_positionLinedUp"]).size().rename("n").reset_index()
        teams = base.groupby("nflId").team.agg(lambda s: sorted(set(s)))
        info = self.players.set_index("nflId")[["displayName", "officialPosition", "weight", "height_in", "height",
                                                 "collegeName", "birthDate"]].copy()
        info["teams"] = teams
        info["rol_principal"] = role_n.idxmax(axis=1)
        info = info[info.teams.notna()]
        self.info = info
        self.role_n = role_n
        self.lined = lined
        # z dentro de posición para burst
        rs = self.rush_season
        peers = rs[rs.n_model >= 50]
        self.burst_peers = peers.groupby("pos").burst_med.apply(lambda s: s.dropna().to_numpy()).to_dict()

    # --------------------------------------------------------------- laboratorio (precalculado)
    def _quintiles(self, df, var, q=5):
        d = df.dropna(subset=[var]).copy()
        d["q"] = pd.qcut(d[var], q, labels=False, duplicates="drop")
        t = d.groupby("q").agg(lo=(var, "min"), hi=(var, "max"), n=("pressure", "size"),
                               k=("pressure", "sum")).reset_index()
        t["tasa"] = t.k / t.n
        lo, hi = wilson(t.k, t.n)
        t["ic_lo"], t["ic_hi"] = lo, hi
        t["q"] = t.q + 1
        return t

    def _lab(self):
        R, M, m3 = self.R, self.Mpop, self.m3
        lab = {}
        # 1. reproducción y verificación de quintiles
        variants = [
            ("A", "Análisis exploratorio original",
             "Todos los snaps de Pass Rush con tracking (incluye LB/DB en blitz); burst = s máx. entre frames 0 y 10 "
             "dentro de la ventana snap→pase", R, "burst_v1"),
            ("B", "Población del modelo, definición original",
             "EDGE e IDL, con snap, ventana válida, posición del QB y sin conversiones de 2 pts; misma definición original",
             M, "burst_v1"),
            ("C", "Población del modelo, definición final",
             "EDGE e IDL (misma población que la regresión); burst = s máx. entre frames 1 y 10 tras el snap",
             M, "burst"),
        ]
        qv = []
        for key, name, desc, df, var in variants:
            t = self._quintiles(df, var)
            low, high = t.iloc[0], t.iloc[-1]
            qv.append({"clave": key, "nombre": name, "descripcion": desc, "n": int(t.n.sum()),
                       "jugadores": int(df.dropna(subset=[var]).nflId.nunique()),
                       "q1": float(low.tasa), "q5": float(high.tasa), "razon": float(high.tasa / low.tasa),
                       "quintiles": records(t)})
        lab["quintiles_versiones"] = qv
        # 2. quintiles y deciles por grupo
        lab["quintiles_grupo"] = {g: records(self._quintiles(M[M.grupo == g], "burst")) for g in RUSH_GROUPS}
        lab["deciles_grupo"] = {g: records(self._quintiles(M[M.grupo == g], "burst", 10)) for g in RUSH_GROUPS}
        # 3. distribución por posición
        bins = np.arange(0, 7.25, 0.25)
        dist = []
        for i in range(len(bins) - 1):
            row = {"x": float(bins[i] + 0.125)}
            for pos in ["DE", "OLB", "DT", "NT"]:
                s = M[M.officialPosition == pos].burst
                row[pos] = float(((s >= bins[i]) & (s < bins[i + 1])).mean() * 100)
            dist.append(row)
        lab["distribucion"] = dist
        qt = M.groupby("officialPosition").burst.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
        lab["cuantiles_posicion"] = records(qt.reset_index().rename(columns={"10%": "p10", "25%": "p25", "50%": "p50",
                                                                            "75%": "p75", "90%": "p90"}))
        # 4. efectos del modelo
        sd = {g: float(M[M.grupo == g].burst.std()) for g in RUSH_GROUPS}
        eff = {
            "edge_yd": m3.lincomb({"burst_c": 1}),
            "idl_yd": m3.lincomb({"burst_c": 1, "burst_x_idl": 1}),
            "inter_yd": m3.lincomb({"burst_x_idl": 1}),
            "edge_sd": m3.lincomb({"burst_c": sd["EDGE"]}),
            "idl_sd": m3.lincomb({"burst_c": sd["IDL"], "burst_x_idl": sd["IDL"]}),
            "peso_edge": m3.lincomb({"w10": 1}),
            "peso_idl": m3.lincomb({"w10": 1, "w10_x_idl": 1}),
        }
        lab["efectos"] = eff
        lab["sd_burst"] = sd
        # 5. curvas de probabilidad con IC (delta method)
        ctxm = self.X3[CTX].mean().to_dict()
        curves, pctl = {}, []
        for g, idl in [("EDGE", 0), ("IDL", 1)]:
            sub = M[M.grupo == g]
            wg = (sub.weight.mean() - self.cst["weight"]) / 10
            lo_, hi_ = sub.burst.quantile([0.02, 0.98])

            def xrow(bv):
                bc = bv - self.cst["burst"]
                return {"burst_c": bc, "w10": wg, "idl": idl, "burst_x_idl": bc * idl, "w10_x_idl": wg * idl, **ctxm}
            pts = []
            for bv in np.linspace(lo_, hi_, 30):
                p, l, h = m3.predict_row(xrow(bv))
                pts.append({"burst": float(bv), "p": p, "lo": l, "hi": h})
            curves[g] = pts
            for q in [0.1, 0.25, 0.5, 0.75, 0.9]:
                bv = float(sub.burst.quantile(q))
                p, l, h = m3.predict_row(xrow(bv))
                pctl.append({"grupo": g, "percentil": int(q * 100), "burst": bv, "p": p, "lo": l, "hi": h})
        lab["curvas"] = curves
        lab["percentiles_prob"] = pctl
        # 6. dispersión jugador
        rs = self.rush_season
        sc = rs[rs.grupo.isin(RUSH_GROUPS) & (rs.n_model >= 50)][
            ["nflId", "nombre", "pos", "grupo", "equipo", "snaps", "n_model", "burst_med", "tasa", "o_e"]]
        lab["dispersion"] = records(sc)
        lab["correlaciones"] = {g: corr_test(sc[sc.grupo == g].burst_med, sc[sc.grupo == g].tasa)
                                for g in RUSH_GROUPS}
        # 7. habitual vs por jugada
        m4 = self.m4
        lab["entre_dentro"] = [
            {"componente": "Burst habitual (promedio del jugador)", "grupo": "EDGE", **m4.lincomb({"between": 1})},
            {"componente": "Burst habitual (promedio del jugador)", "grupo": "IDL",
             **m4.lincomb({"between": 1, "between_x_idl": 1})},
            {"componente": "Burst de la jugada vs su promedio", "grupo": "EDGE", **m4.lincomb({"within": 1})},
            {"componente": "Burst de la jugada vs su promedio", "grupo": "IDL",
             **m4.lincomb({"within": 1, "within_x_idl": 1})},
        ]
        # 8. burst vs getoff vs aceleración inicial
        alt = []
        labels = {"burst": "Burst (velocidad máx. 1 s)", "getoff": "Getoff (desplazamiento 1 s)",
                  "a_max_1s": "Aceleración máx. 1 s"}
        for var, (mod, sub) in self.alt.items():
            row = {"metrica": var, "nombre": labels[var], "auc": mod.auc, "n": mod.n}
            for g, w in [("EDGE", {"burst_c": 1}), ("IDL", {"burst_c": 1, "burst_x_idl": 1})]:
                s_ = float(sub[sub.grupo == g][var].std())
                r = mod.lincomb({k: v * s_ for k, v in w.items()})
                row[f"or_sd_{g}"], row[f"lo_{g}"], row[f"hi_{g}"], row[f"p_{g}"] = r["OR"], r["lo"], r["hi"], r["p"]
                row[f"sd_{g}"] = s_
            alt.append(row)
        lab["metricas_alternativas"] = alt
        cm = M[["burst", "getoff", "a_max_1s"]].corr()
        lab["corr_metricas"] = clean({a: {b: float(cm.loc[a, b]) for b in cm.columns} for a in cm.index})
        # 9. forest plot y ajuste
        forest = []
        for c in self.m3.cols:
            r = m3.lincomb({c: 1})
            forest.append({"termino": c, "etiqueta": TERM_LABELS.get(c, c), **r})
        lab["forest"] = forest
        Mm = M.assign(p_hat=m3.p)
        Mm["dec"] = pd.qcut(Mm.p_hat, 10, labels=False)
        cal = Mm.groupby("dec").agg(n=("pressure", "size"), esperado=("p_hat", "mean"),
                                    observado=("pressure", "mean"), O=("pressure", "sum"), E=("p_hat", "sum"))
        hl = float(((cal.O - cal.E) ** 2 / (cal.E * (1 - cal.E / cal.n))).sum())
        lab["calibracion"] = records(cal.reset_index()[["dec", "n", "esperado", "observado"]])
        lab["ajuste"] = {"n": m3.n, "jugadores": m3.G, "partidos": int(M.gameId.nunique()), "auc": m3.auc,
                         "mcfadden": 1 - m3.ll / m3.ll0, "brier": m3.brier, "brier_base": m3.brier0,
                         "hosmer_lemeshow": hl, "phi": self.phi,
                         "tasa_base": float(M.pressure.mean()),
                         "por_grupo": records(M.groupby("grupo").agg(n=("pressure", "size"),
                                                                     jugadores=("nflId", "nunique"),
                                                                     presiones=("pressure", "sum"),
                                                                     tasa=("pressure", "mean")).reset_index())}
        lab["robustez"] = self.robust
        self.lab = clean(lab)

    # ======================================================================== consultas
    def filtros(self):
        g = self.games.sort_values(["week", "gameDate", "gameId"])
        teams = sorted(set(self.games.homeTeamAbbr) | set(self.games.visitorTeamAbbr))
        return clean({
            "equipos": teams,
            "semanas": sorted(self.games.week.unique().tolist()),
            "partidos": [{"gameId": int(r.gameId), "semana": int(r.week),
                          "etiqueta": f"S{r.week} · {r.visitorTeamAbbr} @ {r.homeTeamAbbr}",
                          "equipos": [r.visitorTeamAbbr, r.homeTeamAbbr]} for r in g.itertuples()],
            "grupos": [{"valor": "TODOS", "etiqueta": "Todas las posiciones"},
                       {"valor": "EDGE", "etiqueta": "EDGE (DE, OLB)", "lado": "defensa"},
                       {"valor": "IDL", "etiqueta": "IDL (DT, NT)", "lado": "defensa"},
                       {"valor": "OT", "etiqueta": "OT (tackles)", "lado": "ofensiva"},
                       {"valor": "IOL", "etiqueta": "IOL (G, C)", "lado": "ofensiva"}],
        })

    @staticmethod
    def _f(df, week=None, game=None, team=None, team_col="team"):
        m = pd.Series(True, index=df.index)
        if week:
            m &= df.week == week
        if game:
            m &= df.gameId == game
        if team:
            m &= df[team_col] == team
        return df[m]

    def _team_table(self, Rf, Bf, PLf):
        Rk = Rf.assign(kp=Rf.pressure * Rf.modelable)
        r = Rk.groupby("team").agg(rush_snaps=("pressure", "size"), presiones=("pressure", "sum"),
                                   esperadas=("p_hat", "sum"), n_model=("modelable", "sum"), k_model=("kp", "sum"))
        burst = Rf[Rf.modelable].groupby("team").burst.mean().rename("burst_medio")
        b = Bf.groupby("team").agg(block_snaps=("lost", "size"), perdidos=("lost", "sum"), permitidas=("allowed", "sum"))
        pl = PLf.groupby("possessionTeam").agg(dropbacks=("pressured", "size"), presionadas=("pressured", "sum"))
        t = r.join(burst, how="outer").join(b, how="outer").join(pl, how="outer")
        t["tasa_presion"] = t.presiones / t.rush_snaps
        t["oe"] = t.k_model / t.esperadas.replace(0, np.nan)
        t["efectividad"] = 1 - t.perdidos / t.block_snaps
        t["presion_permitida"] = t.presionadas / t.dropbacks
        t["tasa_permitida_bloq"] = t.permitidas / t.block_snaps
        t.index.name = "equipo"
        t = t.reset_index()
        for c, asc in [("tasa_presion", False), ("efectividad", False), ("presion_permitida", True),
                       ("burst_medio", False), ("oe", False)]:
            t["rk_" + c] = t[c].rank(ascending=asc, method="min")
        return t

    def resumen(self, team=None, grupo="TODOS", week=None, game=None, min_snaps=50):
        R, B, PL = self.R, self.B, self.PL
        # el filtro de posición se aplica solo al lado de la pelota que corresponde
        Rg = R[R.grupo == grupo] if grupo in RUSH_GROUPS else R
        Bg = B[B.grupo == grupo] if grupo in BLOCK_GROUPS else B
        Rw, Bw = self._f(Rg, week, game), self._f(Bg, week, game)
        PLw = self._f(PL, week, game, team_col="possessionTeam")
        teams = self._team_table(Rw, Bw, PLw)
        Rf, Bf = self._f(Rw, team=team), self._f(Bw, team=team)
        PLf = self._f(PLw, team=team, team_col="possessionTeam")
        mu_all = self._f(B[B.defId.notna()], week, game)
        if grupo in RUSH_GROUPS:
            mu_all = mu_all[mu_all.def_grupo == grupo]
        elif grupo in BLOCK_GROUPS:
            mu_all = mu_all[mu_all.grupo == grupo]
        if team:
            mu_all = mu_all[(mu_all.team == team) | (mu_all.opp == team)]
        n_mu = len(mu_all)
        rp = self.agg_rushers(Rf)
        bp = self.agg_blockers(Bf)
        rq = rp[rp.snaps >= min_snaps] if len(rp) else rp
        bq = bp[bp.snaps >= min_snaps] if len(bp) else bp
        plays_ids = pd.concat([Rf[["gameId", "playId"]], Bf[["gameId", "playId"]]]).drop_duplicates()
        k_r, n_r = int(Rf.pressure.sum()), len(Rf)
        Mf = Rf[Rf.modelable]
        lo, hi = wilson(k_r, n_r) if n_r else (np.nan, np.nan)
        lob, hib = wilson(len(Bf) - Bf.lost.sum(), len(Bf)) if len(Bf) else (np.nan, np.nan)
        kpis = {
            "jugadores": int(len(set(rq.nflId if len(rq) else []) | set(bq.nflId if len(bq) else []))),
            "jugadores_total": int(len(set(Rf.nflId) | set(Bf.nflId))),
            "jugadas": int(len(plays_ids)),
            "enfrentamientos": int(n_mu),
            "rush_snaps": n_r, "presiones": k_r,
            "tasa_presion": k_r / n_r if n_r else None, "tasa_presion_lo": lo, "tasa_presion_hi": hi,
            "tasa_esperada": float(Mf.p_hat.mean()) if len(Mf) else None,
            "oe": float(Mf.pressure.sum() / Mf.p_hat.sum()) if len(Mf) else None,
            "block_snaps": int(len(Bf)), "perdidos": int(Bf.lost.sum()) if len(Bf) else 0,
            "efectividad": float(1 - Bf.lost.mean()) if len(Bf) else None, "efectividad_lo": lob,
            "efectividad_hi": hib,
            "tasa_permitida_bloq": float(Bf.allowed.mean()) if len(Bf) else None,
            "dropbacks": int(len(PLf)), "presion_permitida": float(PLf.pressured.mean()) if len(PLf) else None,
            "burst_medio": float(Mf.burst.mean()) if len(Mf) else None,
            "liga": {
                "tasa_presion": float(Rw.pressure.mean()) if len(Rw) else None,
                "efectividad": float(1 - Bw.lost.mean()) if len(Bw) else None,
                "presion_permitida": float(PLw.pressured.mean()) if len(PLw) else None,
                "burst_medio": float(Rw[Rw.modelable].burst.mean()) if Rw.modelable.any() else None,
            },
        }
        tops_r = rq.sort_values("tasa_ajustada", ascending=False).head(10) if len(rq) else rq
        tops_b = bq.sort_values("efectividad_ajustada", ascending=False).head(10) if len(bq) else bq
        obs = self._observaciones(team, grupo, Rf, Bf, rq, bq, teams, min_snaps)
        return clean({
            "filtros": {"equipo": team, "grupo": grupo, "semana": week, "partido": game, "min_snaps": min_snaps,
                        "lado_filtrado": "defensa" if grupo in RUSH_GROUPS else (
                            "ofensiva" if grupo in BLOCK_GROUPS else None)},
            "kpis": kpis,
            "equipos": records(teams),
            "top_rushers": records(tops_r) if len(tops_r) else [],
            "top_bloqueadores": records(tops_b) if len(tops_b) else [],
            "observaciones": obs,
            "hallazgo": self._hallazgo(),
        })

    def _hallazgo(self):
        lab = self.lab
        A = next(v for v in lab["quintiles_versiones"] if v["clave"] == "A")
        C = next(v for v in lab["quintiles_versiones"] if v["clave"] == "C")
        return {"original": {k: A[k] for k in ["q1", "q5", "razon", "n", "descripcion"]},
                "modelo": {k: C[k] for k in ["q1", "q5", "razon", "n", "descripcion"]},
                "efectos": lab["efectos"], "percentiles_prob": lab["percentiles_prob"],
                "ajuste": {k: lab["ajuste"][k] for k in ["auc", "n", "jugadores"]}}

    def _burst_gain(self, nflId):
        """Probabilidad estimada si el burst de cada jugada se moviera a la mediana de su posición."""
        sub = self.R[(self.R.nflId == nflId) & self.R.modelable]
        if sub.empty:
            return None
        pos = sub.officialPosition.iloc[0]
        peers = self.Mpop[self.Mpop.officialPosition == pos].burst
        target = float(peers.median())
        delta = target - float(sub.burst.median())
        b = self.m3.b
        slope = b[self.m3.idx("burst_c")] + (b[self.m3.idx("burst_x_idl")] if sub.grupo.iloc[0] == "IDL" else 0)
        p_new = logistic(sub.eta + slope * delta).mean()
        return {"mediana_pos": target, "delta": delta, "p_actual": float(sub.p_hat.mean()), "p_mediana": float(p_new)}

    def _observaciones(self, team, grupo, Rf, Bf, rq, bq, teams, min_snaps):
        out = []
        pct = lambda x: f"{x * 100:.1f}%"
        if len(rq):
            t = rq.sort_values("tasa_ajustada", ascending=False).iloc[0]
            out.append({"tipo": "fortaleza", "titulo": "Generador de presión más efectivo",
                        "texto": f"{t.nombre} ({t.pos}, {t.equipo}): {int(t.presiones)} presiones en {int(t.snaps)} "
                                 f"oportunidades ({pct(t.tasa)}, IC95 {pct(t.ic_lo)}–{pct(t.ic_hi)}). "
                                 f"Tasa ajustada por muestra: {pct(t.tasa_ajustada)}.",
                        "nflId": int(t.nflId)})
            above = rq[(rq.o_e >= 1.3) & (rq.p_aj < 0.05)].sort_values("z_aj", ascending=False).head(3)
            for t in above.itertuples():
                out.append({"tipo": "fortaleza", "titulo": "Más presión de la esperada por el modelo",
                            "texto": f"{t.nombre} ({t.pos}, {t.equipo}): {pct(t.tasa_model_obs)} observada vs "
                                     f"{pct(t.tasa_esp)} esperada según su burst, peso, posición y contexto "
                                     f"(O/E {t.o_e:.2f}, p={t.p_aj:.3f}, {int(t.n_model)} jugadas).",
                            "nflId": int(t.nflId)})
            below = rq[(rq.o_e <= 0.7) & (rq.n_model >= min_snaps)].sort_values("z_aj").head(3)
            for t in below.itertuples():
                sig = "diferencia significativa" if t.p_aj < 0.05 else f"p={t.p_aj:.2f}, no concluyente"
                out.append({"tipo": "revision", "titulo": "Requiere análisis técnico: debajo de lo esperado",
                            "texto": f"{t.nombre} ({t.pos}, {t.equipo}): {pct(t.tasa_model_obs)} observada vs "
                                     f"{pct(t.tasa_esp)} esperada (O/E {t.o_e:.2f}, {sig}). Su explosividad no "
                                     f"explica el resultado; revisar técnica, plan y asignaciones.",
                            "nflId": int(t.nflId)})
            cand = []
            for t in rq[rq.grupo.isin(RUSH_GROUPS)].itertuples():
                pc = pct_rank(self.burst_peers.get(t.pos, []), t.burst_med)
                if pc is not None and pc <= 25:
                    cand.append((pc, t))
            for pc, t in sorted(cand, key=lambda z: z[0])[:3]:
                g = self._burst_gain(t.nflId)
                extra = ""
                if g:
                    extra = (f" Si su burst estuviera en la mediana de los {t.pos} ({g['mediana_pos']:.2f} yd/s), el "
                             f"modelo estimaría {pct(g['p_mediana'])} vs {pct(g['p_actual'])} actual "
                             f"(asociación, no efecto garantizado).")
                out.append({"tipo": "oportunidad", "titulo": "Oportunidad en explosividad inicial",
                            "texto": f"{t.nombre} ({t.pos}, {t.equipo}): burst mediano {t.burst_med:.2f} yd/s, "
                                     f"percentil {pc:.0f} entre los {t.pos}. Tasa de presión {pct(t.tasa)}.{extra}",
                            "nflId": int(t.nflId)})
        bq_ol = bq[bq.grupo.isin(BLOCK_GROUPS)] if len(bq) else bq
        if len(bq_ol):
            t = bq_ol.sort_values("efectividad_ajustada").iloc[0]
            sub = Bf[(Bf.nflId == t.nflId) & Bf.def_grupo.notna()]
            vs = sub.groupby("def_grupo").lost.agg(["mean", "size"])
            vs = vs[vs["size"] >= 20]
            extra = ""
            if len(vs) >= 1:
                w = vs["mean"].idxmax()
                extra = f" Su peor perfil rival: {w} ({pct(vs.loc[w, 'mean'])} perdidos en {int(vs.loc[w, 'size'])})."
            out.append({"tipo": "revision", "titulo": "Bloqueador con más dificultades",
                        "texto": f"{t.nombre} ({t.pos}, {t.equipo}): efectividad {pct(t.efectividad)} en "
                                 f"{int(t.snaps)} bloqueos ({int(t.perdidos)} perdidos, {int(t.permitidas)} presiones "
                                 f"permitidas).{extra}",
                        "nflId": int(t.nflId)})
            mu = Bf[Bf.def_grupo.notna()]
            if len(mu):
                cross = mu.groupby(["grupo", "def_grupo"]).lost.agg(["mean", "size"]).reset_index()
                cross = cross[(cross["size"] >= 30) & (cross.grupo != "OTRO") & (cross.def_grupo != "OTRO")]
                if len(cross) >= 2:
                    w = cross.sort_values("mean", ascending=False).iloc[0]
                    out.append({"tipo": "situacion", "titulo": "Enfrentamiento más difícil para la línea",
                                "texto": f"{w.grupo} contra {w.def_grupo}: {pct(w['mean'])} de bloqueos perdidos en "
                                         f"{int(w['size'])} enfrentamientos, el más alto de esta selección."})
        if len(Rf) >= 200:
            for lab, m in [("3.er/4.º down", Rf.down >= 3), ("play action", Rf.pff_playAction == 1)]:
                a, b = Rf[m], Rf[~m]
                if len(a) >= 50 and len(b) >= 50:
                    la, ha = wilson(a.pressure.sum(), len(a))
                    lb, hb = wilson(b.pressure.sum(), len(b))
                    sep = "sin traslape de IC95" if (la > hb or lb > ha) else "con IC95 traslapados"
                    out.append({"tipo": "situacion", "titulo": f"Presión en {lab}",
                                "texto": f"{pct(a.pressure.mean())} con {lab} ({len(a)} oportunidades) vs "
                                         f"{pct(b.pressure.mean())} sin ({len(b)}), {sep}."})
        if team and len(teams) > 1:
            row = teams[teams.equipo == team]
            if len(row):
                r = row.iloc[0]
                n = int(teams.tasa_presion.notna().sum())
                bits = []
                if pd.notna(r.tasa_presion):
                    bits.append(f"{int(r.rk_tasa_presion)}.º de {n} en presión generada ({pct(r.tasa_presion)})")
                if pd.notna(r.efectividad):
                    bits.append(f"{int(r.rk_efectividad)}.º en efectividad de bloqueo ({pct(r.efectividad)})")
                if pd.notna(r.presion_permitida):
                    bits.append(f"{int(r.rk_presion_permitida)}.º en menor presión permitida "
                                f"({pct(r.presion_permitida)} de dropbacks)")
                if bits:
                    out.append({"tipo": "contexto", "titulo": f"{team} frente a los demás equipos",
                                "texto": "; ".join(bits) + "."})
        return clean(out)

    # --------------------------------------------------------------- jugadores
    def lista_jugadores(self):
        info = self.info
        rn = self.role_n
        df = info[["displayName", "officialPosition", "teams", "rol_principal"]].copy()
        df["rush"] = rn.get("Pass Rush", 0)
        df["block"] = rn.get("Pass Block", 0)
        df["grupo"] = df.officialPosition.map({**RUSH_GROUP, **BLOCK_GROUP}).fillna("OTRO")
        df = df.reset_index()
        df["teams"] = df.teams.apply(lambda t: "/".join(t))
        return records(df.sort_values("displayName"))

    def jugador(self, nflId: int):
        if nflId not in self.info.index:
            return None
        inf = self.info.loc[nflId]
        pos = inf.officialPosition
        lined = self.lined[self.lined.nflId == nflId].sort_values("n", ascending=False)
        tot = lined.n.sum()
        roles = self.role_n.loc[nflId]
        role = "Pass Rush" if roles.get("Pass Rush", 0) >= 20 else (
            "Pass Block" if roles.get("Pass Block", 0) >= 20 else inf.rol_principal)
        out = {"info": {"nflId": nflId, "nombre": inf.displayName, "posicion": pos, "equipos": inf.teams,
                        "peso": inf.weight, "altura_in": inf.height_in, "altura": inf.height,
                        "universidad": inf.collegeName, "nacimiento": inf.birthDate, "rol_analizado": role,
                        "grupo": {**RUSH_GROUP, **BLOCK_GROUP}.get(pos, "OTRO"),
                        "alineaciones": [{"pos": r.pff_positionLinedUp, "n": int(r.n), "pct": r.n / tot}
                                         for r in lined.head(4).itertuples()],
                        "roles": {k: int(v) for k, v in roles.items() if v > 0}}}
        # física
        pp = self.phys_player
        me = pp[(pp.nflId == nflId) & (pp.pff_role == role)]
        peers = pp[(pp.officialPosition == pos) & (pp.pff_role == role) & (pp.n >= 20)]
        fis = []
        if len(me):
            me = me.iloc[0]
            for key, label, unit, desc in PHYS:
                v = me[key]
                fis.append({"clave": key, "etiqueta": label, "unidad": unit, "descripcion": desc, "valor": v,
                            "media_pos": peers[key].mean(), "mediana_pos": peers[key].median(),
                            "p25_pos": peers[key].quantile(0.25), "p75_pos": peers[key].quantile(0.75),
                            "percentil": pct_rank(peers[key].to_numpy(), v)})
        out["fisico"] = {"rol": role, "jugadas": int(me["n"]) if len(fis) else 0, "pares": int(len(peers)),
                         "metricas": fis,
                         "distribucion_burst": {"valores": peers.burst.dropna().round(3).tolist(),
                                                "jugador": me["burst"] if len(fis) else None}}
        # rendimiento como rusher
        R = self.R[self.R.nflId == nflId]
        if len(R):
            rs = self.rush_season
            me_r = rs[rs.nflId == nflId].iloc[0]
            peer_r = rs[(rs.pos == pos) & (rs.snaps >= 50)]
            out["rush"] = {**me_r.to_dict(),
                           "pct_tasa": pct_rank(peer_r.tasa.to_numpy(), me_r.tasa) if len(peer_r) else None,
                           "media_pos_tasa": peer_r.tasa.mean() if len(peer_r) else None,
                           "mediana_pos_tasa": peer_r.tasa.median() if len(peer_r) else None,
                           "pct_oe": pct_rank(peer_r.o_e.to_numpy(), me_r.o_e) if len(peer_r) else None,
                           "pares": int(len(peer_r)),
                           "distribucion_tasa": peer_r.tasa.round(4).tolist(),
                           "ganancia_burst": self._burst_gain(nflId),
                           "situaciones": self._situaciones_rush(R),
                           "por_semana": records(R.groupby("week").agg(snaps=("pressure", "size"),
                                                                       presiones=("pressure", "sum"),
                                                                       esperadas=("p_hat", "sum"),
                                                                       burst=("burst", "median")).reset_index()
                                                 .assign(tasa=lambda d: d.presiones / d.snaps))}
        else:
            out["rush"] = None
        # rendimiento como bloqueador
        Bp = self.B[self.B.nflId == nflId]
        if len(Bp):
            bs = self.block_season
            me_b = bs[bs.nflId == nflId].iloc[0]
            peer_b = bs[(bs.pos == pos) & (bs.snaps >= 50)]
            bt = Bp.groupby(Bp.pff_blockType.fillna("Sin dato")).agg(n=("lost", "size"), perdidos=("lost", "sum"))
            bt["tasa_perdida"] = bt.perdidos / bt.n
            ref_bt = self.B[self.B.officialPosition == pos].groupby("pff_blockType").lost.mean().rename("ref_pos")
            bt = bt.join(ref_bt).reset_index().rename(columns={"pff_blockType": "tipo"})
            if "tipo" not in bt.columns:
                bt = bt.rename(columns={bt.columns[0]: "tipo"})
            mu = Bp[Bp.def_grupo.notna()]
            ref = self.B[(self.B.officialPosition == pos) & self.B.def_grupo.notna()]
            vg = mu.groupby("def_grupo").agg(n=("lost", "size"), perdidos=("lost", "sum")).join(
                ref.groupby("def_grupo").lost.mean().rename("ref_pos"))
            vg["tasa_perdida"] = vg.perdidos / vg.n
            lo, hi = wilson(vg.perdidos, vg.n)
            vg["ic_lo"], vg["ic_hi"] = lo, hi
            vp = mu.groupby("def_pos").agg(n=("lost", "size"), perdidos=("lost", "sum")).join(
                ref.groupby("def_pos").lost.mean().rename("ref_pos"))
            vp["tasa_perdida"] = vp.perdidos / vp.n
            riv = mu.groupby(["defId", "def_name", "def_pos"]).agg(n=("lost", "size"), perdidos=("lost", "sum"),
                                                                   permitidas=("allowed", "sum")).reset_index()
            riv = riv.sort_values(["n", "perdidos"], ascending=False).head(10)
            # peso del rival
            mu2 = mu.dropna(subset=["def_weight"]).copy()
            mu2["dif_peso"] = mu2.def_weight - mu2.weight
            bins = [-500, -40, -10, 10, 500]
            labs = ["Rival ≥40 lb más ligero", "10–40 lb más ligero", "Peso similar (±10 lb)", "Rival >10 lb más pesado"]
            mu2["rango"] = pd.cut(mu2.dif_peso, bins, labels=labs)
            dp = mu2.groupby("rango", observed=False).agg(n=("lost", "size"), perdidos=("lost", "sum")).reset_index()
            dp["tasa_perdida"] = dp.perdidos / dp.n.replace(0, np.nan)
            out["block"] = {**me_b.to_dict(),
                            "pct_efectividad": pct_rank(peer_b.efectividad.to_numpy(), me_b.efectividad)
                            if len(peer_b) else None,
                            "media_pos": peer_b.efectividad.mean() if len(peer_b) else None,
                            "mediana_pos": peer_b.efectividad.median() if len(peer_b) else None,
                            "pares": int(len(peer_b)),
                            "distribucion_efectividad": peer_b.efectividad.round(4).tolist(),
                            "tipos_bloqueo": records(bt.sort_values("n", ascending=False)),
                            "vs_grupo": records(vg.reset_index()),
                            "vs_posicion": records(vp.reset_index().sort_values("n", ascending=False)),
                            "vs_peso": records(dp),
                            "rivales": records(riv)}
        else:
            out["block"] = None
        return clean(out)

    def _situaciones_rush(self, R):
        ref = self.R[self.R.grupo == R.grupo.iloc[0]]
        rows = []
        defs = [
            ("Down", "1.º–2.º down", lambda d: d.down.isin([1, 2])),
            ("Down", "3.º–4.º down", lambda d: d.down >= 3),
            ("Play action", "Sin play action", lambda d: d.pff_playAction == 0),
            ("Play action", "Con play action", lambda d: d.pff_playAction == 1),
            ("Bloqueo recibido", "Sin bloqueador asignado", lambda d: d.n_blockers == 0),
            ("Bloqueo recibido", "Un bloqueador", lambda d: d.n_blockers == 1),
            ("Bloqueo recibido", "Doble equipo", lambda d: d.n_blockers >= 2),
            ("Rushers en la jugada", "4 o menos", lambda d: d.n_rush <= 4),
            ("Rushers en la jugada", "5 o más (blitz)", lambda d: d.n_rush >= 5),
        ]
        for cat, lab, f in defs:
            s = R[f(R)]
            r = ref[f(ref)]
            n, k = len(s), int(s.pressure.sum())
            lo, hi = wilson(k, n) if n else (np.nan, np.nan)
            rows.append({"categoria": cat, "situacion": lab, "n": n, "presiones": k, "tasa": k / n if n else None,
                         "ic_lo": lo, "ic_hi": hi, "ref_grupo": float(r.pressure.mean()) if len(r) else None})
        return clean(rows)


engine = Engine()
