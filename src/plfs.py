"""Load PLFS first-visit person files and apply MoSPI's weighting rules.

Weight rules (from each release's README):
  annual rounds, CY2022, CY2024: mult / no_qtr / (100 if nss == nsc else 200)
  CY2025:                        mult / 100
"""
import os, re, zipfile
import numpy as np
import pandas as pd

RAW = os.environ.get("PLFS_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "raw"))

# label -> (zip file, person-file suffix, weight rule)
ROUNDS = {
    "2017-18": ("CSV_PLFS_July2017_June2018.zip", "hh_per_fv_2017-18.csv", "combined"),
    "2018-19": ("PLFS_2018_19_CSV.zip", "PerV1_2018-19.csv", "combined"),
    "2019-20": ("CSV_PLFS_19_20.zip", "PERFV_2019-20.csv", "combined"),
    "2020-21": ("CSV_Unit_level_data_PLFS_July2020_June2021.zip", "/perv1.csv", "combined"),
    "2021-22": ("PLFS_Data_2021-22_CSV.zip", "/perv1.csv", "combined"),
    "2022-23": ("_PLFS___July__2022-_June2023.zip", "/perv1.csv", "combined"),
    "2023-24": ("CSV_data_PLFS_2023_2024.zip", "/perv1.csv", "combined"),
    "CY2024": ("Key_Employment_Unemployment_Indicators_for_calendar_year_2024.zip", "cperv1.csv", "combined"),
    "CY2025": ("_PLFS__Calendar_Year_2025__Jan-Dec25_.zip", "cperv12025.csv", "simple"),
}

# column-name patterns (matched case-insensitively against the CSV header)
PATTERNS = {
    "sec": r"^(b1q3|sector$|sec$)", "st": r"^(state|st$)", "sex": r"^(b4q5|sex$)",
    "age": r"^(b4q6|age$)", "mar": r"^(b4q7|marital_status$|marst$)",
    "edu": r"^(b4q8|general_education_level$|gedu_lvl$)",
    "pas": r"^(b5pt1q3|principal_status_code$|pas$)", "sas": r"^(b5pt2q3|subsidiary_status_code$|sas$)",
    "mult": r"^(mult|subsample_multiplier$)", "nss": r"^(nss(?!_reg)|ns_count_sector_stratum_substratum_subsample$)",
    "nsc": r"^(nsc|ns_count_sector_stratum_substratum$)", "nq": r"^(no_qtr|state_sector_stratum_substra)",
}
WORKER = {"11", "12", "21", "31", "41", "51"}
STATUS = {"11": "Own-account / employer", "12": "Own-account / employer", "21": "Unpaid helper",
          "31": "Regular wage/salary", "41": "Casual labour", "51": "Casual labour"}


def _find(zf, suffix):
    return next(n for n in zf.namelist() if n.lower().endswith(suffix.lower()))


def load(label, adults_only=True):
    zname, suffix, rule = ROUNDS[label]
    with zipfile.ZipFile(os.path.join(RAW, zname)) as zf:
        member = _find(zf, suffix)
        with zf.open(member) as fh:
            header = list(pd.read_csv(fh, nrows=0, encoding="latin-1").columns)
        cols = {}
        for key, pat in PATTERNS.items():
            if rule == "simple" and key in ("nss", "nsc", "nq"):
                continue
            cols[key] = next(c for c in header if re.match(pat, c, re.I))
        with zf.open(member) as fh:
            d = pd.read_csv(fh, usecols=list(cols.values()), dtype=str, encoding="latin-1")
    d = d.rename(columns={v: k for k, v in cols.items()}).apply(lambda s: s.str.strip())
    for c in ["sec", "sex", "age", "mar", "edu", "mult"] + (["nss", "nsc", "nq"] if rule != "simple" else []):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if rule == "simple":
        d["w"] = d.mult / 100
    else:
        d["w"] = d.mult / d.nq / np.where(d.nss == d.nsc, 100, 200)
    d["suspect"] = d.w > 1_000_000          # 9 Assam records in 2022-23 (see MoSPI clarification note)
    d["round"] = label
    d["emp"] = d.pas.isin(WORKER) | d.sas.isin(WORKER)          # usual status (ps+ss)
    d["unemp"] = ~d.emp & d.pas.isin({"81", "82"})
    d["lf"] = d.emp | d.unemp
    main = d.pas.where(d.pas.isin(WORKER), d.sas.where(d.sas.isin(WORKER)))
    d["status"] = main.map(STATUS)
    d = d[["round", "sec", "st", "sex", "age", "mar", "edu", "w", "suspect", "emp", "unemp", "lf", "status"]]
    return d[d.age >= 15] if adults_only else d


def rate(g, col):
    return 100 * (g[col] * g.w).sum() / g.w.sum()
