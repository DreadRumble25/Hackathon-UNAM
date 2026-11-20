"""Consultas de los módulos 4 a 8 de NFL Matchup Analytics.

Todas parten de las tablas que construye backend.engine al arrancar.
Unidades: rusher x jugada y bloqueador x jugada; nunca frames.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backend.engine import (BLOCK_GROUPS, CTX, RUSH_GROUP, RUSH_GROUPS, TERM_LABELS, Engine, clean, pct_rank,
                            records, wilson)


def _rate_ci(k, n):
    lo, hi = wilson(k, n)
    return float(lo), float(hi)


# =============================================================== Módulo 4: observado vs esperado
def observado_esperado(e: Engine, grupo: str = "TODOS", min_snaps: int = 100, equipo: str | None = None):
    rs = e.rush_season
    d = rs[rs.grupo.isin(RUSH_GROUPS) & (rs.n_model >= min_snaps)].copy()
    if grupo in RUSH_GROUPS:
        d = d[d.grupo == grupo]
    if equipo:
        d = d[d.equipo.str.split("/").apply(lambda t: equipo in t)]
    sd = np.sqrt(d["var"] * e.phi)
    d["oe_lo"] = ((d.k_model - 1.96 * sd) / d.esperadas).clip(lower=0)
    d["oe_hi"] = (d.k_model + 1.96 * sd) / d.esperadas
    lo, hi = wilson(d.k_model, d.n_model)
    d["obs_lo"], d["obs_hi"] = lo, hi
    d["dif_100"] = (d.tasa_model_obs - d.tasa_esp) * 100
    d["pct_burst"] = [pct_rank(e.burst_peers.get(p, []), b) for p, b in zip(d.pos, d.burst_med)]
    d["clasificacion"] = np.select(
        [(d.p_aj < 0.05) & (d.o_e > 1), (d.p_aj < 0.05) & (d.o_e < 1), d.o_e >= 1.2, d.o_e <= 0.8],
        ["Por encima (p<0.05)", "Por debajo (p<0.05)", "Tendencia por encima", "Tendencia por debajo"],
        "Dentro de lo esperado")
    cols = ["nflId", "nombre", "pos", "grupo", "equipo", "peso", "snaps", "n_model", "k_model", "esperadas",
            "tasa_model_obs", "obs_lo", "obs_hi", "tasa_esp", "dif_100", "o_e", "oe_lo", "oe_hi", "z_aj", "p_aj",
            "tasa_ajustada", "burst_med", "pct_burst", "clasificacion"]
    d = d.sort_values("z_aj", ascending=False)
    n = len(d)
    k_up = int(((d.p_aj < 0.05) & (d.o_e > 1)).sum())
    k_dn = int(((d.p_aj < 0.05) & (d.o_e < 1)).sum())
    return clean({
        "jugadores": records(d[cols]),
        "resumen": {"n": n, "sobre": k_up, "bajo": k_dn, "esperados_por_azar": 0.05 * n,
                    "bonferroni": 0.05 / n if n else None,
                    "sobreviven_bonferroni": int((d.p_aj < 0.05 / max(n, 1)).sum()), "phi": e.phi,
                    "min_snaps": min_snaps},
    })


# =============================================================== Módulo 5: enfrentamientos
def _ol_vs_rush(e: Engine):
    B = e.B
    return B[B.defId.notna() & (B.def_role == "Pass Rush")]


def enfrentamientos_resumen(e: Engine, equipo: str | None = None, min_pair: int = 10):
    M = _ol_vs_rush(e)
    if equipo:
        M = M[(M.team == equipo) | (M.opp == equipo)]
    out = {"n": int(len(M)), "parejas": int(M.groupby(["nflId", "defId"]).ngroups),
           "bloqueadores": int(M.nflId.nunique()), "defensores": int(M.defId.nunique()),
           "perdido": float(M.lost.mean()) if len(M) else None,
           "permitido": float(M.allowed.mean()) if len(M) else None}
    OL = M[M.officialPosition.isin(["T", "G", "C"]) & M.def_grupo.isin(RUSH_GROUPS)]
    cross = OL.groupby(["officialPosition", "def_grupo"]).agg(n=("lost", "size"), perdidos=("lost", "sum"),
                                                              permitidas=("allowed", "sum")).reset_index()
    cross["tasa"] = cross.perdidos / cross.n
    lo, hi = wilson(cross.perdidos, cross.n)
    cross["ic_lo"], cross["ic_hi"] = lo, hi
    out["cruce"] = records(cross)

    bt = M.groupby("pff_blockType").agg(n=("lost", "size"), perdidos=("lost", "sum"),
                                        permitidas=("allowed", "sum")).reset_index()
    bt["tasa"] = bt.perdidos / bt.n
    bt["tasa_perm"] = bt.permitidas / bt.n
    out["tipos"] = records(bt[bt.n >= 20].sort_values("n", ascending=False))

    # físico del enfrentamiento, estratificado para no confundir con la posición
    S = OL.copy()
    S["estrato"] = np.where((S.officialPosition == "T") & (S.def_grupo == "EDGE"), "OT vs EDGE",
                            np.where(S.officialPosition.isin(["G", "C"]) & (S.def_grupo == "IDL"), "IOL vs IDL", None))
    S = S[S.estrato.notna()]
    S["dif_peso"] = S.def_weight - S.weight
    S["dif_altura"] = S.def_height - S.height_in
    fis = {}
    for est, sub in S.groupby("estrato"):
        rows = {}
        for var, bins, labels in [
            ("dif_peso", [-500, -60, -30, 0, 500], ["≤ −60 lb", "−60 a −30", "−30 a 0", "> 0 (defensor más pesado)"]),
            ("dif_altura", [-50, -3, -1, 1, 50], ["≤ −3 in", "−3 a −1", "±1 in", "> 1 in"]),
        ]:
            sub_ = sub.assign(r=pd.cut(sub[var], bins, labels=labels))
            t = sub_.groupby("r", observed=False).agg(n=("lost", "size"), perdidos=("lost", "sum")).reset_index()
            t["tasa"] = t.perdidos / t.n.replace(0, np.nan)
            lo, hi = wilson(t.perdidos, t.n.replace(0, np.nan))
            t["ic_lo"], t["ic_hi"] = lo, hi
            rows[var] = records(t.rename(columns={"r": "rango"}))
        b = sub.dropna(subset=["def_burst"]).copy()
        b["q"] = pd.qcut(b.def_burst, 5, labels=False, duplicates="drop") + 1
        t = b.groupby("q").agg(lo=("def_burst", "min"), hi=("def_burst", "max"), n=("lost", "size"),
                               perdidos=("lost", "sum")).reset_index()
        t["tasa"] = t.perdidos / t.n
        l_, h_ = wilson(t.perdidos, t.n)
        t["ic_lo"], t["ic_hi"] = l_, h_
        rows["burst_defensor"] = records(t)
        fis[est] = rows
    out["fisico"] = fis

    # dobles equipos
    R = e.R[e.R.grupo.isin(RUSH_GROUPS)]
    if equipo:
        R = R[R.team == equipo]
    R = R.assign(bloqueo=np.select([R.n_blockers == 0, R.n_blockers == 1], ["Sin bloqueador", "Un bloqueador"],
                                   "Doble equipo"))
    dt = R.groupby(["grupo", "bloqueo"]).agg(n=("pressure", "size"), presiones=("pressure", "sum"),
                                             burst=("burst", "mean")).reset_index()
    dt["tasa"] = dt.presiones / dt.n
    lo, hi = wilson(dt.presiones, dt.n)
    dt["ic_lo"], dt["ic_hi"] = lo, hi
    out["dobles"] = records(dt)
    dbl = R.groupby("nflId").agg(nombre=("displayName", "first"), pos=("officialPosition", "first"),
                                 equipo=("team", "first"), snaps=("pressure", "size"),
                                 dobles=("n_blockers", lambda s: int((s >= 2).sum()))).reset_index()
    dbl["pct_doble"] = dbl.dobles / dbl.snaps
    out["mas_doblados"] = records(dbl[dbl.snaps >= 100].sort_values("pct_doble", ascending=False).head(12))

    pr = M.groupby(["nflId", "defId"]).agg(bloqueador=("displayName", "first"), pos_b=("officialPosition", "first"),
                                           equipo_b=("team", "first"), defensor=("def_name", "first"),
                                           pos_d=("def_pos", "first"), equipo_d=("opp", "first"),
                                           n=("lost", "size"), perdidos=("lost", "sum"),
                                           permitidas=("allowed", "sum"),
                                           pres_def=("def_pressure", "sum")).reset_index()
    pr = pr[pr.n >= min_pair]
    pr["tasa"] = pr.perdidos / pr.n
    out["parejas_top"] = records(pr.sort_values("n", ascending=False).head(25))
    out["parejas_dominadas"] = records(pr.sort_values(["tasa", "n"], ascending=False).head(12))
    return clean(out)


def rivales(e: Engine, nflId: int):
    M = _ol_vs_rush(e)
    if (M.nflId == nflId).any():
        sub, lado = M[M.nflId == nflId], "bloqueador"
        g = sub.groupby("defId").agg(nombre=("def_name", "first"), pos=("def_pos", "first"), equipo=("opp", "first"),
                                     n=("lost", "size"), perdidos=("lost", "sum")).reset_index().rename(
            columns={"defId": "nflId"})
    elif (M.defId == nflId).any():
        sub, lado = M[M.defId == nflId], "defensor"
        g = sub.groupby("nflId").agg(nombre=("displayName", "first"), pos=("officialPosition", "first"),
                                     equipo=("team", "first"), n=("lost", "size"),
                                     perdidos=("lost", "sum")).reset_index()
    else:
        return {"lado": None, "rivales": []}
    return clean({"lado": lado, "rivales": records(g.sort_values("n", ascending=False))})


def _phys(e: Engine, nflId: int, role: str):
    pp = e.phys_player
    me = pp[(pp.nflId == nflId) & (pp.pff_role == role)]
    if me.empty:
        return {}
    me = me.iloc[0]
    peers = pp[(pp.officialPosition == me.officialPosition) & (pp.pff_role == role) & (pp.n >= 20)]
    return {k: {"valor": me[k], "percentil": pct_rank(peers[k].to_numpy(), me[k])}
            for k in ["burst", "getoff", "a_max_1s", "s_max", "a_max", "dist"]}


def pareja(e: Engine, blk: int, dfn: int):
    M = _ol_vs_rush(e)
    sub = M[(M.nflId == blk) & (M.defId == dfn)].copy()
    if sub.empty:
        return None
    b_all = e.B[e.B.nflId == blk]
    r_all = e.R[e.R.nflId == dfn]
    pb, pd_ = e.info.loc[blk], e.info.loc[dfn]
    n, k = len(sub), int(sub.lost.sum())
    lo, hi = _rate_ci(k, n)
    rd = e.rush_season[e.rush_season.nflId == dfn]
    bd = e.block_season[e.block_season.nflId == blk]
    sub["partido"] = sub.gameId.map(e.game_label)
    sub["resultado"] = np.select(
        [sub.pff_sackAllowed == 1, sub.pff_hitAllowed == 1, sub.pff_hurryAllowed == 1, sub.pff_beatenByDefender == 1],
        ["Sack permitido", "Hit permitido", "Hurry permitido", "Superado sin presión"], "Bloqueo ganado")
    sub["doble"] = sub.n_blk_def >= 2
    hist = sub.sort_values(["week", "gameId", "playId"])[
        ["gameId", "playId", "week", "partido", "quarter", "gameClock", "down", "yardsToGo", "pff_blockType",
         "resultado", "lost", "def_pressure", "def_burst", "doble", "pff_playAction", "playDescription"]]
    bt = sub.groupby(sub.pff_blockType.fillna("Sin dato")).agg(n=("lost", "size"), perdidos=("lost", "sum")).reset_index()
    bt["tasa"] = bt.perdidos / bt.n
    sd = sub[sub.doble]
    ss = sub[~sub.doble]
    return clean({
        "bloqueador": {"nflId": blk, "nombre": pb.displayName, "pos": pb.officialPosition, "equipos": pb.teams,
                       "peso": pb.weight, "altura_in": pb.height_in, "fisico": _phys(e, blk, "Pass Block"),
                       "efectividad_total": float(1 - b_all.lost.mean()) if len(b_all) else None,
                       "efectividad_ajustada": float(bd.efectividad_ajustada.iloc[0]) if len(bd) else None,
                       "snaps_total": int(len(b_all))},
        "defensor": {"nflId": dfn, "nombre": pd_.displayName, "pos": pd_.officialPosition, "equipos": pd_.teams,
                     "peso": pd_.weight, "altura_in": pd_.height_in, "fisico": _phys(e, dfn, "Pass Rush"),
                     "tasa_total": float(r_all.pressure.mean()) if len(r_all) else None,
                     "tasa_ajustada": float(rd.tasa_ajustada.iloc[0]) if len(rd) else None,
                     "o_e": float(rd.o_e.iloc[0]) if len(rd) and pd.notna(rd.o_e.iloc[0]) else None,
                     "snaps_total": int(len(r_all))},
        "resumen": {"n": n, "perdidos": k, "tasa_perdida": k / n, "ic_lo": lo, "ic_hi": hi,
                    "efectividad": 1 - k / n, "permitidas": int(sub.allowed.sum()),
                    "sacks": int(sub.pff_sackAllowed.sum()), "pres_def": int(sub.def_pressure.sum()),
                    "partidos": int(sub.gameId.nunique()), "dobles": int(sub.doble.sum()),
                    "perdida_doble": float(sd.lost.mean()) if len(sd) else None,
                    "perdida_solo": float(ss.lost.mean()) if len(ss) else None,
                    "burst_def_med": float(sub.def_burst.median()) if sub.def_burst.notna().any() else None,
                    "dif_peso": float(pd_.weight - pb.weight), "dif_altura": float(pd_.height_in - pb.height_in)},
        "tipos": records(bt.sort_values("n", ascending=False)),
        "historial": records(hist),
    })


# =============================================================== Módulo 7: simulador
def modelo(e: Engine):
    m = e.m3
    M = e.Mpop
    grupos = {}
    for g in RUSH_GROUPS:
        s = M[M.grupo == g]
        grupos[g] = {"n": int(len(s)), "peso_media": float(s.weight.mean()),
                     "peso_min": float(s.weight.quantile(0.02)), "peso_max": float(s.weight.quantile(0.98)),
                     "burst_pct": {str(q): float(s.burst.quantile(q / 100)) for q in [2, 10, 25, 50, 75, 90, 98]},
                     "dqb_media": float(s.dqb_start.mean()), "dqb_min": float(s.dqb_start.quantile(0.02)),
                     "dqb_max": float(s.dqb_start.quantile(0.98)), "tasa": float(s.pressure.mean())}
    return clean({
        "terminos": ["(intercepto)"] + m.cols,
        "etiquetas": {**TERM_LABELS, "(intercepto)": "Intercepto"},
        "coef": m.b.tolist(), "vcov": m.V.tolist(),
        "centros": e.cst, "ctx_media": e.X3[CTX].mean().to_dict(),
        "ytg": {"min": 1, "max": int(M.yardsToGo.quantile(0.99)), "media": float(M.yardsToGo.mean())},
        "n_rush": {"valores": sorted(int(v) for v in M.n_rush.dropna().unique() if 3 <= v <= 7),
                   "media": float(M.n_rush.mean())},
        "grupos": grupos,
        "ajuste": {k: e.lab["ajuste"][k] for k in ["n", "jugadores", "auc", "mcfadden", "tasa_base"]},
        "jugadores": records(e.rush_season[e.rush_season.grupo.isin(RUSH_GROUPS) & (e.rush_season.n_model >= 50)][
            ["nflId", "nombre", "pos", "grupo", "equipo", "peso", "burst_med", "tasa", "tasa_esp", "n_model"]]
            .sort_values("nombre")),
    })


# =============================================================== Módulo 8: reportes
def reporte(e: Engine, equipo: str, min_snaps: int = 50):
    R, B, PL = e.R, e.B, e.PL
    teams = e._team_table(R, B, PL)
    row = teams[teams.equipo == equipo]
    if row.empty:
        return None
    row = row.iloc[0]
    n_t = int(teams.tasa_presion.notna().sum())
    metr = []
    for key, label, fmt, mejor in [("tasa_presion", "Presión generada", "pct", "alto"),
                                   ("oe", "Presión observada / esperada", "num", "alto"),
                                   ("burst_medio", "Burst promedio de rushers", "num", "alto"),
                                   ("efectividad", "Efectividad de bloqueo", "pct", "alto"),
                                   ("presion_permitida", "Dropbacks con presión permitida", "pct", "bajo")]:
        rk = int(row["rk_" + key]) if pd.notna(row["rk_" + key]) else None
        metr.append({"clave": key, "etiqueta": label, "formato": fmt, "valor": row[key],
                     "liga": float(teams[key].mean()), "rango": rk, "de": n_t,
                     "nivel": None if rk is None else ("fortaleza" if rk <= 8 else "area" if rk > n_t - 8 else "medio")})

    # rushers del equipo
    rp = e.agg_rushers(R[R.team == equipo])
    rp = rp[rp.snaps >= min_snaps]
    rush = []
    for t in rp.sort_values("tasa_ajustada", ascending=False).itertuples():
        pb = pct_rank(e.burst_peers.get(t.pos, []), t.burst_med) if t.grupo in RUSH_GROUPS else None
        pr = pct_rank(e.rate_peers.get(t.pos, []), t.tasa_ajustada)
        tags = []
        if pr is not None and pr >= 75:
            tags.append(("fortaleza", f"Presión en el percentil {pr:.0f} de los {t.pos}"))
        if pd.notna(t.o_e) and pd.notna(t.p_aj):
            if t.o_e > 1 and t.p_aj < 0.05:
                tags.append(("fortaleza", f"Supera lo esperado por el modelo (O/E {t.o_e:.2f}, p={t.p_aj:.3f})"))
            elif t.o_e < 1 and t.p_aj < 0.05:
                tags.append(("evaluar", f"Por debajo de lo esperado (O/E {t.o_e:.2f}, p={t.p_aj:.3f})"))
        if pb is not None:
            if pb >= 75:
                tags.append(("fisico", f"Explosividad alta: burst en el percentil {pb:.0f}"))
            elif pb <= 25:
                tags.append(("evaluar", f"Explosividad baja: burst en el percentil {pb:.0f}"))
            if pb >= 60 and pd.notna(t.o_e) and t.o_e < 0.85:
                tags.append(("evaluar", "Es explosivo pero produce menos de lo esperado: revisar técnica de manos, "
                                        "plan de rush y asignaciones"))
            if pb <= 40 and pd.notna(t.o_e) and t.o_e > 1.2:
                tags.append(("fortaleza", "Produce por encima de lo esperado con explosividad modesta: "
                                          "posible ventaja técnica"))
        if pr is not None and pr <= 25:
            tags.append(("evaluar", f"Presión en el percentil {pr:.0f} de los {t.pos}"))
        rush.append({"nflId": t.nflId, "nombre": t.nombre, "pos": t.pos, "grupo": t.grupo, "peso": t.peso,
                     "snaps": t.snaps, "presiones": t.presiones, "sacks": t.sacks, "tasa": t.tasa,
                     "ic_lo": t.ic_lo, "ic_hi": t.ic_hi, "tasa_esp": t.tasa_esp, "o_e": t.o_e, "p_aj": t.p_aj,
                     "tasa_ajustada": t.tasa_ajustada, "burst": t.burst_med, "pct_burst": pb, "pct_tasa": pr,
                     "notas": [{"tipo": a, "texto": b} for a, b in tags]})

    # bloqueadores del equipo
    Bt = B[B.team == equipo]
    bp = e.agg_blockers(Bt)
    bp = bp[bp.snaps >= min_snaps]
    ref = B[B.def_grupo.isin(RUSH_GROUPS)].groupby(["officialPosition", "def_grupo"]).lost.mean()
    blk = []
    for t in bp.sort_values("efectividad_ajustada", ascending=False).itertuples():
        pe = pct_rank(e.eff_peers.get(t.pos, []), t.efectividad_ajustada)
        tags = []
        if pe is not None and pe >= 75:
            tags.append(("fortaleza", f"Efectividad en el percentil {pe:.0f} de los {t.pos}"))
        if pe is not None and pe <= 25:
            tags.append(("evaluar", f"Efectividad en el percentil {pe:.0f} de los {t.pos}"))
        s = Bt[(Bt.nflId == t.nflId) & Bt.def_grupo.isin(RUSH_GROUPS)]
        vs = s.groupby("def_grupo").lost.agg(["mean", "size"])
        for g, r_ in vs.iterrows():
            rv = ref.get((t.pos, g))
            if r_["size"] >= 40 and rv is not None and r_["mean"] >= 1.5 * rv and r_["mean"] - rv >= 0.04:
                lo, hi = _rate_ci(r_["mean"] * r_["size"], r_["size"])
                tags.append(("evaluar", f"Pierde {r_['mean'] * 100:.1f}% contra {g} (IC95 {lo * 100:.1f}–{hi * 100:.1f}%) "
                                        f"vs {rv * 100:.1f}% de su posición, en {int(r_['size'])} enfrentamientos"))
        bts = s.groupby("pff_blockType").lost.agg(["mean", "size"])
        bts = bts[bts["size"] >= 25]
        if len(bts):
            w = bts["mean"].idxmax()
            refb = B[(B.officialPosition == t.pos) & (B.pff_blockType == w)].lost.mean()
            if bts.loc[w, "mean"] >= 1.5 * refb and bts.loc[w, "mean"] - refb >= 0.04:
                tags.append(("evaluar", f"Tipo de bloqueo más difícil: {w} ({bts.loc[w, 'mean'] * 100:.1f}% perdidos "
                                        f"vs {refb * 100:.1f}% de su posición)"))
        blk.append({"nflId": t.nflId, "nombre": t.nombre, "pos": t.pos, "grupo": t.grupo, "peso": t.peso,
                    "snaps": t.snaps, "permitidas": t.permitidas, "perdidos": t.perdidos,
                    "efectividad": t.efectividad, "ic_lo": t.ic_lo, "ic_hi": t.ic_hi,
                    "efectividad_ajustada": t.efectividad_ajustada, "pct": pe,
                    "notas": [{"tipo": a, "texto": b} for a, b in tags]})

    # situaciones
    def split(df, col, defs):
        out = []
        for lab, f in defs:
            s = df[f(df)]
            n, k = len(s), int(s[col].sum())
            lo, hi = _rate_ci(k, n) if n else (None, None)
            out.append({"situacion": lab, "n": n, "tasa": k / n if n else None, "ic_lo": lo, "ic_hi": hi})
        return out
    defs = [("1.º–2.º down", lambda d: d.down.isin([1, 2])), ("3.º–4.º down", lambda d: d.down >= 3),
            ("Con play action", lambda d: d.pff_playAction == 1), ("Sin play action", lambda d: d.pff_playAction == 0)]
    Rd = R[R.team == equipo]
    rush_sit = split(Rd, "pressure", defs + [("4 rushers o menos", lambda d: d.n_rush <= 4),
                                             ("5+ rushers (blitz)", lambda d: d.n_rush >= 5)])
    rush_sit_l = split(R, "pressure", defs + [("4 rushers o menos", lambda d: d.n_rush <= 4),
                                              ("5+ rushers (blitz)", lambda d: d.n_rush >= 5)])
    for a, b in zip(rush_sit, rush_sit_l):
        a["liga"] = b["tasa"]
    PLt = PL[PL.possessionTeam == equipo].merge(e.plays[["gameId", "playId", "pff_playAction"]], on=["gameId", "playId"])
    PLl = PL.merge(e.plays[["gameId", "playId", "pff_playAction"]], on=["gameId", "playId"])
    off_sit = split(PLt, "pressured", defs)
    off_l = split(PLl, "pressured", defs)
    for a, b in zip(off_sit, off_l):
        a["liga"] = b["tasa"]

    fort = [m_ for m_ in metr if m_["nivel"] == "fortaleza"]
    areas = [m_ for m_ in metr if m_["nivel"] == "area"]
    revisar = [r_ for r_ in rush if any(n_["tipo"] == "evaluar" for n_ in r_["notas"])] + \
              [b_ for b_ in blk if any(n_["tipo"] == "evaluar" for n_ in b_["notas"])]
    return clean({"equipo": equipo, "min_snaps": min_snaps, "metricas": metr, "fortalezas": fort, "areas": areas,
                  "rushers": rush, "bloqueadores": blk, "situaciones_defensa": rush_sit,
                  "situaciones_ofensiva": off_sit, "a_revisar": len(revisar),
                  "partidos": int(R[R.team == equipo].gameId.nunique())})
