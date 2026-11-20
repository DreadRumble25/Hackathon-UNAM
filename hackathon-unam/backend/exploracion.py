"""Exploración de solo lectura de data/.

Uso: .venv\\Scripts\\python backend\\exploracion.py
El tracking (122 archivos, ~850 MB) se procesa archivo por archivo para no
cargarlo completo en memoria. No escribe nada en data/.
"""
import glob
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 100)
pd.set_option("display.max_rows", 300)

RAIZ = Path(__file__).resolve().parent.parent
D = next(RAIZ.glob("data/**/games.csv")).parent


def h(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100, flush=True)


def perfil(df, nombre):
    h(f"{nombre}: {df.shape[0]:,} filas x {df.shape[1]} columnas")
    p = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "nulos": df.isna().sum(),
        "%nulos": (df.isna().mean() * 100).round(2),
        "unicos": df.nunique(),
    })
    print(p)
    print(f"Filas duplicadas exactas: {df.duplicated().sum():,}")
    num = df.select_dtypes("number")
    if not num.empty:
        print("\nEstadísticas numéricas:")
        print(num.describe().T.round(3))


h("ARCHIVOS")
for f in sorted(D.rglob("*")):
    if f.is_file() and "tracking_" not in f.name:
        print(f"{f.relative_to(D)}  {f.suffix}  {f.stat().st_size:,} bytes")
tfiles = sorted(glob.glob(str(D / "tracking" / "tracking_*.csv")))
print(f"tracking/: {len(tfiles)} archivos .csv, {sum(Path(t).stat().st_size for t in tfiles):,} bytes")

games = pd.read_csv(D / "games.csv")
players = pd.read_csv(D / "players.csv")
plays = pd.read_csv(D / "plays.csv")
pff = pd.read_csv(D / "pffScoutingData.csv")

for df, n in [(games, "games"), (players, "players"), (plays, "plays"), (pff, "pffScoutingData")]:
    perfil(df, n)

h("CLAVES")
print("games.gameId duplicado:", games.gameId.duplicated().sum())
print("players.nflId duplicado:", players.nflId.duplicated().sum())
print("players.displayName repetido:", players.displayName.duplicated(keep=False).sum())
print(players[players.displayName.duplicated(keep=False)].sort_values("displayName").to_string())
print("plays (gameId,playId) duplicado:", plays.duplicated(["gameId", "playId"]).sum())
print("pff (gameId,playId,nflId) duplicado:", pff.duplicated(["gameId", "playId", "nflId"]).sum())

# ------------------------------------------------------------------ TRACKING
h("TRACKING (procesado por archivo)")
NUM = ["x", "y", "s", "a", "dis", "o", "dir"]
n_rows = 0
nulls = None
dtypes = None
cols = None
ev_c, team_c, dir_c = Counter(), Counter(), Counter()
dup_full = dup_key = dup_ball = ball_rows = football_rows = 0
bad_file = 0
viol = Counter()
keys_play, keys_pp = [], []
frames_play, players_play = [], []
dt_c = Counter()
s_sum = {c: 0.0 for c in NUM}
s_sq = {c: 0.0 for c in NUM}
s_n = {c: 0 for c in NUM}
s_min = {c: np.inf for c in NUM}
s_max = {c: -np.inf for c in NUM}
muestras = []
dis_xy = []  # (dis, dist calculada) muestras
play_dir_mix = 0
snap_plays = 0
end_ev = {"tackle", "out_of_bounds", "touchdown", "qb_sack", "pass_outcome_incomplete",
          "pass_outcome_caught", "pass_outcome_interception", "qb_strip_sack", "pass_outcome_touchdown"}
end_plays = 0
ev_order_bad = 0
plays_no_ball = 0
jersey_null = 0
time_bad = 0
rng = np.random.default_rng(0)

for i, t in enumerate(tfiles):
    df = pd.read_csv(t)
    if dtypes is None:
        dtypes = df.dtypes.astype(str)
        cols = list(df.columns)
        nulls = df.isna().sum()
    else:
        nulls += df.isna().sum()
    n_rows += len(df)
    gid = int(Path(t).stem.split("_")[1])
    if list(df.gameId.unique()) != [gid]:
        bad_file += 1
    ev_c.update(df.event.fillna("<NaN>").tolist())
    team_c.update(df.team.fillna("<NaN>").tolist())
    dir_c.update(df.playDirection.fillna("<NaN>").tolist())
    dup_full += df.duplicated().sum()
    dup_key += df.dropna(subset=["nflId"]).duplicated(["gameId", "playId", "nflId", "frameId"]).sum()
    ball = df[df.nflId.isna()]
    ball_rows += len(ball)
    football_rows += (df.team == "football").sum()
    dup_ball += ball.duplicated(["gameId", "playId", "frameId"]).sum()
    viol["x<0|x>120"] += ((df.x < 0) | (df.x > 120)).sum()
    viol["y<0|y>53.3"] += ((df.y < 0) | (df.y > 53.3)).sum()
    viol["o fuera 0-360"] += ((df.o < 0) | (df.o > 360)).sum()
    viol["dir fuera 0-360"] += ((df.dir < 0) | (df.dir > 360)).sum()
    viol["s>12 yd/s"] += (df.s > 12).sum()
    viol["|a|>15 yd/s2"] += (df.a.abs() > 15).sum()
    viol["dis>1.5 yd/frame"] += (df.dis > 1.5).sum()
    viol["o nulo jugador"] += df.loc[df.nflId.notna(), "o"].isna().sum()
    for c in NUM:
        v = df[c].dropna().to_numpy(dtype=float)
        s_sum[c] += v.sum(); s_sq[c] += (v ** 2).sum(); s_n[c] += v.size
        if v.size:
            s_min[c] = min(s_min[c], v.min()); s_max[c] = max(s_max[c], v.max())
    muestras.append(df.sample(frac=0.02, random_state=i)[NUM + ["nflId"]])
    kp = df[["gameId", "playId"]].drop_duplicates()
    keys_play.append(kp)
    keys_pp.append(df.dropna(subset=["nflId"])[["gameId", "playId", "nflId"]].drop_duplicates())
    g = df.groupby("playId")
    frames_play.append(g.frameId.max())
    players_play.append(df.dropna(subset=["nflId"]).groupby("playId").nflId.nunique())
    play_dir_mix += (g.playDirection.nunique() > 1).sum()
    plays_no_ball += len(kp) - ball.playId.nunique()
    jersey_null += df.loc[df.nflId.notna(), "jerseyNumber"].isna().sum()
    # eventos por jugada
    evs = df[df.event.notna() & (df.event != "None")].groupby("playId").event.apply(set)
    snap_plays += evs.apply(lambda s: "ball_snap" in s).sum()
    end_plays += evs.apply(lambda s: bool(s & end_ev)).sum()
    # snap debe ocurrir antes que pass_forward (si ambos existen)
    e2 = df[df.event.isin(["ball_snap", "pass_forward"])].groupby(["playId", "event"]).frameId.min().unstack()
    if {"ball_snap", "pass_forward"} <= set(e2.columns):
        ev_order_bad += (e2.ball_snap > e2.pass_forward).sum()
    # tiempo entre frames y consistencia dis
    ts = pd.to_datetime(df.time, errors="coerce", utc=True)
    time_bad += ts.isna().sum()
    pj = df.assign(ts=ts).dropna(subset=["nflId"]).sort_values(["playId", "nflId", "frameId"])
    gg = pj.groupby(["playId", "nflId"])
    dt = gg.ts.diff().dt.total_seconds().dropna().round(2)
    dt_c.update(dt.tolist())
    dx = gg.x.diff(); dy = gg.y.diff()
    calc = np.hypot(dx, dy)
    m = calc.notna() & pj.dis.notna()
    idx = rng.choice(m.sum(), size=min(20000, m.sum()), replace=False)
    dis_xy.append(np.c_[pj.dis[m].to_numpy()[idx], calc[m].to_numpy()[idx]])
    if i % 20 == 0:
        print(f"  ...{i + 1}/{len(tfiles)}", flush=True)

print(f"\nFilas totales: {n_rows:,} | columnas: {len(cols)}")
print(pd.DataFrame({"dtype": dtypes, "nulos": nulls, "%nulos": (nulls / n_rows * 100).round(3)}))
print("\nEstadísticas numéricas exactas (count, mean, std, min, max) + cuartiles sobre muestra 2%:")
samp = pd.concat(muestras)
q = samp[NUM].quantile([0.25, 0.5, 0.75]).T
est = pd.DataFrame({
    "count": s_n,
    "mean": {c: s_sum[c] / s_n[c] for c in NUM},
    "std": {c: np.sqrt(s_sq[c] / s_n[c] - (s_sum[c] / s_n[c]) ** 2) for c in NUM},
    "min": s_min, "max": s_max,
}).join(q)
print(est.round(3))
print("\nSolo jugadores (muestra 2%):")
print(samp[samp.nflId.notna()][["s", "a", "dis"]].describe().T.round(3))
print("\nFilas duplicadas exactas:", dup_full)
print("Duplicados por (gameId,playId,nflId,frameId) en jugadores:", dup_key)
print("Duplicados del balón por (gameId,playId,frameId):", dup_ball)
print("Filas de balón (nflId nulo):", ball_rows, "| team=='football':", football_rows)
print("Archivos cuyo gameId interno != nombre de archivo:", bad_file)
print("\nevent:\n", pd.Series(ev_c).sort_values(ascending=False).to_string())
print("\nteam:\n", pd.Series(team_c).sort_values(ascending=False).to_string())
print("\nplayDirection:", dict(dir_c))
print("\nViolaciones de rango:", dict(viol))
print("Jugadas con playDirection mixto:", play_dir_mix)
print("Jugadas sin filas de balón:", plays_no_ball)
print("Jersey nulo en jugadores:", jersey_null)
print("time no parseable:", time_bad)
print("Delta entre frames (s), más comunes:", pd.Series(dt_c).sort_values(ascending=False).head(6).to_dict())
dxy = np.vstack(dis_xy)
print("Corr(dis, distancia calculada desde x,y):", round(float(np.corrcoef(dxy[:, 0], dxy[:, 1])[0, 1]), 4),
      "| error abs medio:", round(float(np.abs(dxy[:, 0] - dxy[:, 1]).mean()), 4))
fp = pd.concat(frames_play)
pp = pd.concat(players_play)
print("\nFrames por jugada:\n", fp.describe().round(1).to_string())
print("Jugadores distintos por jugada:\n", pp.describe().round(1).to_string())
print("Jugadas con != 22 jugadores:", (pp != 22).sum(), pp[pp != 22].value_counts().to_dict())

# ------------------------------------------------------------------ RELACIONES
h("RELACIONES ENTRE ARCHIVOS")
kt = pd.concat(keys_play).drop_duplicates()
ptk = pd.concat(keys_pp).drop_duplicates()
g_t = set(kt.gameId)
print("games sin tracking:", len(set(games.gameId) - g_t), "| tracking sin games:", len(g_t - set(games.gameId)))
print("plays.gameId no en games:", (~plays.gameId.isin(games.gameId)).sum())
print("pff.gameId no en games:", (~pff.gameId.isin(games.gameId)).sum())
kp = plays[["gameId", "playId"]].drop_duplicates()
kf = pff[["gameId", "playId"]].drop_duplicates()


def anti(a, b):
    return len(a.merge(b, how="left", indicator=True).query("_merge=='left_only'"))


print(f"jugadas: plays={len(kp):,} tracking={len(kt):,} pff={len(kf):,}")
print("plays sin tracking:", anti(kp, kt), "| tracking sin plays:", anti(kt, kp))
print("plays sin pff:", anti(kp, kf), "| pff sin plays:", anti(kf, kp))
print("pff.nflId no en players:", (~pff.nflId.isin(players.nflId)).sum())
tid = ptk.nflId.unique()
print("tracking nflId no en players:", (~pd.Series(tid).isin(players.nflId)).sum(), "de", len(tid))
print("players que no aparecen en tracking:", (~players.nflId.isin(tid)).sum())
pk = pff[["gameId", "playId", "nflId"]].drop_duplicates()
m = ptk.merge(pk, how="outer", indicator=True)
print("(jugada, jugador) tracking vs pff:", m._merge.value_counts().to_dict())
bp = pff.pff_nflIdBlockedPlayer.dropna()
print("pff_nflIdBlockedPlayer no en players:", (~bp.isin(players.nflId)).sum())
bpk = pff.dropna(subset=["pff_nflIdBlockedPlayer"])[["gameId", "playId", "pff_nflIdBlockedPlayer"]]
bpk = bpk.rename(columns={"pff_nflIdBlockedPlayer": "nflId"})
print("bloqueado que no está en la misma jugada de pff:", anti(bpk, pk))
for c in ["foulNFLId1", "foulNFLId2", "foulNFLId3"]:
    s = plays[c].dropna()
    print(f"plays.{c} no en players:", (~s.isin(players.nflId)).sum(), "de", len(s))
teams = set(games.homeTeamAbbr) | set(games.visitorTeamAbbr)
print("Equipos en games:", len(teams), sorted(teams))
print("possession/defensive fuera de games:", (set(plays.possessionTeam) | set(plays.defensiveTeam)) - teams)
print("team de tracking fuera de games:", set(team_c) - teams - {"football"})
pg = plays.merge(games, on="gameId")
ok = ((pg.possessionTeam == pg.homeTeamAbbr) & (pg.defensiveTeam == pg.visitorTeamAbbr)) | \
     ((pg.possessionTeam == pg.visitorTeamAbbr) & (pg.defensiveTeam == pg.homeTeamAbbr))
print("plays cuyos equipos no coinciden con el partido:", (~ok).sum())
print("Jugadas por partido:\n", plays.groupby("gameId").size().describe().round(1).to_string())
print("Jugadores pff por jugada:\n", pff.groupby(["gameId", "playId"]).size().describe().round(1).to_string())

# ------------------------------------------------------------------ CATEGORÍAS
h("VALORES DE VARIABLES CATEGÓRICAS")
for c in ["quarter", "down", "passResult", "offenseFormation", "dropBackType", "pff_playAction",
          "pff_passCoverage", "pff_passCoverageType", "foulName1", "defendersInBox"]:
    print(f"\n-- plays.{c}\n", plays[c].value_counts(dropna=False).head(30).to_string())
print("\n-- personnelO (top 10)\n", plays.personnelO.value_counts(dropna=False).head(10).to_string())
print("\n-- personnelD (top 10)\n", plays.personnelD.value_counts(dropna=False).head(10).to_string())
print("\n-- players.officialPosition\n", players.officialPosition.value_counts(dropna=False).to_string())
print("\n-- players.height\n", players.height.value_counts(dropna=False).to_string())
print("\n-- pff_role\n", pff.pff_role.value_counts(dropna=False).to_string())
print("\n-- pff_positionLinedUp\n", pff.pff_positionLinedUp.value_counts(dropna=False).to_string())
print("\n-- pff_blockType\n", pff.pff_blockType.value_counts(dropna=False).to_string())
print("\n-- pff_role x indicadores no nulos")
ind = ["pff_hit", "pff_hurry", "pff_sack", "pff_beatenByDefender", "pff_hitAllowed",
       "pff_hurryAllowed", "pff_sackAllowed", "pff_blockType", "pff_nflIdBlockedPlayer"]
print(pff.groupby("pff_role")[ind].count().to_string())
print("\n-- sumas de indicadores por rol")
print(pff.groupby("pff_role")[ind[:7]].sum().to_string())
print("\ngames.week:", games.week.value_counts().sort_index().to_dict())
print("games.gameTimeEastern:", games.gameTimeEastern.value_counts().to_dict())

# ------------------------------------------------------------------ CALIDAD
h("CALIDAD")
gd = pd.to_datetime(games.gameDate, format="%m/%d/%Y", errors="coerce")
print("gameDate no parseable:", gd.isna().sum(), "| rango:", gd.min().date(), "->", gd.max().date())
bfmt = ~players.birthDate.dropna().str.match(r"^\d{4}-\d{2}-\d{2}$")
print("birthDate con formato distinto de YYYY-MM-DD:", bfmt.sum(), players.birthDate.dropna()[bfmt].head(5).tolist())
bd = pd.to_datetime(players.birthDate, errors="coerce", format="mixed")
age = (pd.Timestamp("2021-09-09") - bd).dt.days / 365.25
print("Edad al 2021-09-09:", age.describe().round(1).to_dict())
print("gameClock no MM:SS:", (~plays.gameClock.str.match(r"^\d{1,2}:\d{2}$")).sum())
print("down == 0:", (plays.down == 0).sum(), "| yardsToGo == 0:", (plays.yardsToGo == 0).sum())
print(plays[plays.down == 0][["playDescription", "passResult"]].head(5).to_string())
print("quarter == 5 (tiempo extra):", (plays.quarter == 5).sum())
diff = plays.playResult - (plays.prePenaltyPlayResult + plays.penaltyYards.fillna(0))
print("playResult != prePenaltyPlayResult + penaltyYards:", (diff != 0).sum())
print("foulName1 nulo pero penaltyYards no nulo:", (plays.foulName1.isna() & plays.penaltyYards.notna()).sum())
print("foulName presente sin foulNFLId:", sum((plays[f"foulName{i}"].notna() & plays[f"foulNFLId{i}"].isna()).sum() for i in (1, 2, 3)))
print("yardlineSide nulo con yardlineNumber==50:", (plays.yardlineSide.isna() & (plays.yardlineNumber == 50)).sum(), "de", plays.yardlineSide.isna().sum())
print("playDescription duplicado:", plays.playDescription.duplicated(keep=False).sum())
print(plays[plays.playDescription.duplicated(keep=False)][["gameId", "playId", "playDescription"]].to_string())
print("absoluteYardlineNumber nulo:\n", plays[plays.absoluteYardlineNumber.isna()][["gameId", "playId", "playDescription"]].to_string())
print("passResult vs palabras en descripción:")
for code, word in [("S", "sacked"), ("IN", "INTERCEPTED"), ("I", "incomplete"), ("R", "scramble")]:
    sub = plays[plays.passResult == code]
    print(f"  {code}: {len(sub)} jugadas, sin '{word}' en descripción: {(~sub.playDescription.str.contains(word, case=False)).sum()}")
print("pff_passCoverageType vs pff_passCoverage:\n", pd.crosstab(plays.pff_passCoverage, plays.pff_passCoverageType).to_string())
print("\nFIN", flush=True)
