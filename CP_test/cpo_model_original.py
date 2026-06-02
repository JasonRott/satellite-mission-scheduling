# -*- coding: utf-8 -*-

from docplex.cp.model import (
    CpoModel,
    interval_var,
    presence_of,
    start_of,
    end_of,
    alternative,
    no_overlap,
    if_then,
)
import pandas as pd
import datetime

import import_data_original as data

# =========================
# 0) Helper & basic values
# =========================
M = 200000  # (not used in CP)
contact_dict = data.contact_dict
eclipse_intervals = data.eclipse_intervals
task_dict = data.task_dict
P_H_group_cid_tid = data.P_H_group_cid_tid
S_D_R_group = data.S_D_R_group
File_value = data.File_value
Memory_value = data.Memory_value

total_start_time = min(t["start"] for t in task_dict.values())
max_start=max(t["start"] for t in task_dict.values())

def to_sec(dt):  # seconds relative to total_start_time
    return int((dt - total_start_time).total_seconds())
T_HORIZON = max(
    int((t["start"] - total_start_time).total_seconds()) for t in task_dict.values() 
) + 86400



# Objective weights
W_TASK = 600.0
ALPHA_LATE = 100.0

# =========================
# 1) Create model
# =========================
mdl = CpoModel(name="SatelliteScheduling_CP")

# Expose copies for contact extraction (used by writer)
_dl_copies = {}  # dict: dl_id -> {cid: interval_copy}
_tr_copies = {}  # dict: tr_id -> {cid: interval_copy}

# ---------------------------------------------
# 2) Interval variables (one per task and more)
# ---------------------------------------------
iv_task = {}  # master interval for each task (optional)
is_present = {}  # 0/1 presence expression

for tid, t in task_dict.items():
    ttype = t["type"]
    dur = int(t["duration"])
    if ttype in ("Shoot", "T_maneuver", "P_maneuver", "H_maneuver", "Track"):
        # Fixed-time, optional presence
        st = to_sec(t["start"])
        iv = interval_var(start=st, size=dur, optional=True, name=f"iv_{tid}_{ttype}")
        iv_task[tid] = iv
        is_present[tid] = presence_of(iv)
    elif ttype in ("Download", "Remove"):
        # Windowed, optional presence
        lb = to_sec(t["start"])
        ub = to_sec(t["end"]) - dur
        if ub < lb:
            # Unschedulable window; create a dummy absent var to avoid model crash
            iv = interval_var(optional=True, size=dur, name=f"iv_{tid}_{ttype}_unsched")
        else:
            iv = interval_var(
                start=(lb, ub), size=dur, optional=True, name=f"iv_{tid}_{ttype}"
            )
        iv_task[tid] = iv
        is_present[tid] = presence_of(iv)
    else:
        # Unknown type -> model as fixed optional to keep robustness
        st = to_sec(t["start"])
        iv = interval_var(
            start=st, size=dur, optional=True, name=f"iv_{tid}_{ttype}_unk"
        )
        iv_task[tid] = iv
        is_present[tid] = presence_of(iv)

# ---------------------------------------------------
# 3) No-overlap rules between classes of activities
# ---------------------------------------------------
# A) Maneuvers + Shoot + Download must not overlap pairwise (if present)
maneuver_shoot_download_set = [
    iv_task[tid]
    for tid, t in task_dict.items()
    if t["type"] in ("T_maneuver", "P_maneuver", "H_maneuver", "Shoot", "Download")
]
if maneuver_shoot_download_set:
    mdl.add(no_overlap(maneuver_shoot_download_set))

# B) All Tracks cannot overlap (if that was intended)
track_set = [iv_task[tid] for tid, t in task_dict.items() if t["type"] == "Track"]
if track_set:
    mdl.add(no_overlap(track_set))

# C) Downloads and Removes and Shoots cannot overlap among themselves
dl_rm_sh_set = [
    iv_task[tid] for tid, t in task_dict.items() if t["type"] in ("Download", "Remove", "Shoot")
]
if dl_rm_sh_set:
    mdl.add(no_overlap(dl_rm_sh_set))

# ---------------------------------------------
# 4) Download ↔ contact windows (R-type only) + P/H ties
# ---------------------------------------------
valid_contacts = []
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "P_maneuver":
        if tinfo["info"] != "None":
            valid_contacts.append(tinfo["info"])

for did, dinfo in task_dict.items():
    if dinfo["type"] != "Download":
        continue
    _dl_copies[did] = {}
    d_master = iv_task[did]
    dur = int(dinfo["duration"])
    earliest = dinfo["start"]
    latest = dinfo["end"]

    # Download requires its group's Shoot executed
    grp = dinfo.get("group")
    if grp in S_D_R_group:
        sid = S_D_R_group[grp][0]  # shoot id
        mdl.add(is_present[did] <= is_present[sid])

    # All feasible R-type contacts overlapping the [earliest, latest]
    copies = []
    for cid, c in contact_dict.items():
        if c.get("type") != "R-type":
            continue
        if cid not in valid_contacts:
            continue
        c_rise = c.get("R-typerise")
        c_fade = c.get("R-typefade")
        if c_rise is None or c_fade is None:
            continue
        # Overlap check with the DL window
        if not (c_rise <= latest and c_fade >= earliest):
            continue

        # window for this contact
        lb = max(to_sec(earliest), to_sec(c_rise))
        ub = min(to_sec(latest), to_sec(c_fade)) - dur
        if ub < lb:
            continue

        ivc = interval_var(
            start=(lb, ub), size=dur, optional=True, name=f"iv_dl_{did}_cid{cid}"
        )
        copies.append((cid, ivc))
        _dl_copies[did][cid] = ivc

    # If there are no feasible contacts, the download cannot be scheduled
    if not copies:
        mdl.add(is_present[did] == 0)
        continue

    # Alternative to bind master to exactly one chosen copy
    mdl.add(alternative(d_master, [iv for _, iv in copies]))

    # Tie to P/H of that chosen contact, and precedence relative to P/H
    for cid, ivc in copies:
        if cid not in P_H_group_cid_tid:
            continue

        tid_P, tid_H = P_H_group_cid_tid[cid]
        # P/H presence must be consistent (together on/off)
        mdl.add(is_present[tid_P] == is_present[tid_H])

        # If this contact-copy is used -> P and H must be present
        mdl.add(if_then(presence_of(ivc) == 1, is_present[tid_P] == 1))
        mdl.add(if_then(presence_of(ivc) == 1, is_present[tid_H] == 1))

        # Precedence with P/H (as inequalities for if_then)
        mdl.add(if_then(presence_of(ivc) == 1, end_of(iv_task[tid_P]) <= start_of(ivc)))
        mdl.add(if_then(presence_of(ivc) == 1, end_of(ivc) <= start_of(iv_task[tid_H])))

# ------------------------------------------------------------
# 5) Remove constraints w.r.t. Shoot and *all* Downloads of same group
# ------------------------------------------------------------
for rid, rinfo in task_dict.items():
    if rinfo["type"] != "Remove":
        continue
    r_iv = iv_task[rid]
    grp = rinfo.get("group")

    if grp in S_D_R_group:
        sid = S_D_R_group[grp][0]
        # present together with Shoot
        mdl.add(is_present[rid] == is_present[sid])
        # after Shoot (end(S) <= start(R))
        mdl.add(end_of(iv_task[sid]) <= start_of(r_iv))

        downloads_in_group = [
            d
            for d, t2 in task_dict.items()
            if t2.get("type") == "Download" and t2.get("group") == grp
        ]
        for d in downloads_in_group:
            for cid, ivc in _dl_copies.get(d, {}).items():
                c = contact_dict.get(cid, {})
                cfade = c.get("R-typefade")
                if cfade is not None:
                    mdl.add(
                        if_then(
                            presence_of(ivc) == 1, start_of(r_iv) >= to_sec(cfade) + 6
                        )
                    )

# ------------------------------------------------------------
# 6) Track requirements: assign to one feasible non-R contact (via alternative)
# ------------------------------------------------------------
for tid, t in task_dict.items():
    if t["type"] != "Track":
        continue
    _tr_copies[tid] = {}

    tr_master = iv_task[tid]
    t_start = t["start"]
    t_end = t["end"]
    dur = int(t["duration"])
    st_fixed = to_sec(t_start)

    copies = []
    for cid, c in contact_dict.items():
        # exclude R-type
        if str(c.get("type", "")).startswith("R"):
            continue
        c_start = c.get("rise")
        c_end = c.get("fade")
        if c_start is None or c_end is None:
            continue
        # Require entire track to lie within contact
        if (t_end <= c_end) and (t_start >= c_start):
            ivc = interval_var(
                start=st_fixed, size=dur, optional=True, name=f"iv_tr_{tid}_cid{cid}"
            )
            copies.append(ivc)
            _tr_copies[tid][cid] = ivc

    if copies:
        mdl.add(alternative(tr_master, copies))
    else:
        # No feasible contact -> forbid presence
        mdl.add(presence_of(tr_master) == 0)
# ------------------------------------------------------------
# 7) Eclipse: limit shooting time during eclipse
# ------------------------------------------------------------
z_download_interval = {}

for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download":
        z_download_interval[tid] = {}
        for i, interval in enumerate(eclipse_intervals):
            z_download_interval[tid][i] = mdl.binary_var(name=f"z_download_{tid}_{i}")#binary var

for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download":
        duration = tinfo["duration"]
        mdl.add(
            mdl.sum(z_download_interval[tid][j] for j in range(len(eclipse_intervals))) == is_present[tid]
        )
        for i, interval in enumerate(eclipse_intervals):
            mdl.add(if_then(z_download_interval[tid][i] == 1, start_of(iv_task[tid])>= to_sec(interval["start"])))
            mdl.add(if_then(z_download_interval[tid][i] == 1, end_of(iv_task[tid])  <= to_sec(interval["end"])))

for i, interval in enumerate(eclipse_intervals):
    mdl.add(
        mdl.sum(
            [z_download_interval[tid][i] * tinfo["duration"]
            for tid, tinfo in task_dict.items()
            if tinfo["type"] == "Download"]
        )
        <= 600
    )

# Shoot
for i, interval in enumerate(eclipse_intervals):
    start_i = interval["start"]
    end_i = interval["end"]

    shoot_tids_in_interval = [
        tid
        for tid, tinfo in task_dict.items()
        if tinfo["type"] == "Shoot"
        and tinfo["start"] >= start_i
        and tinfo["end"] <= end_i
    ]

    if shoot_tids_in_interval:  # 若該段有任務才加限制
        mdl.add(
            mdl.sum(
                is_present[tid] * task_dict[tid]["duration"]
                for tid in shoot_tids_in_interval
            )
            <= 480
        )

# ------------------------------------------------------------
# 8) Memory and Photo: limit usage at all times
# ------------------------------------------------------------
# 建立起訖時間變數（Download / Remove / Shoot 需要排定時間）

photo_profile = []
memory_profile = []
iv_sh_rm = {}

for group_id, group_list in S_D_R_group.items():
    shoot_id = group_list[0]
    remove_id = group_list[-1]
    iv = mdl.interval_var()
    mdl.add(mdl.start_of(iv) == start_of(iv_task[shoot_id]))
    mdl.add(mdl.end_of(iv) == end_of(iv_task[remove_id]))
    iv_sh_rm[group_id] = iv
for group_id, iv in iv_sh_rm.items():
    photos = len(S_D_R_group[group_id]) - 2
    memory = task_dict[S_D_R_group[group_id][0]]["memory"]
    photo_profile.append(mdl.pulse(iv, photos))
    memory_profile.append(mdl.pulse(iv, memory))

# 資源限制 (直接對 step function 下界限)
mdl.add(mdl.sum(photo_profile) <= File_value)
mdl.add(mdl.sum(memory_profile) <= Memory_value)
'''
z_memory_interval={}
shoot_start_times = []
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Shoot":
            shoot_start_times.append((tinfo["start"] - total_start_time).total_seconds())
shoot_start_times = sorted(set(shoot_start_times))
memory_intervals = [{"start":shoot_start_times[i],"end": shoot_start_times[i+1]}
                for i in range(len(shoot_start_times)-1)]
max_end = max(
    (tinfo["end"] - total_start_time).total_seconds()
    for tinfo in task_dict.values()
)
memory_intervals.append({"start":shoot_start_times[-1],"end": max_end})
print(memory_intervals)
shoot_to_interval = {}
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Shoot":
        st = (tinfo["start"] - total_start_time).total_seconds()
        for i, interval in enumerate(memory_intervals):
            if interval["start"] <= st < interval["end"]:
                shoot_to_interval[tid] = i
                break
print(shoot_to_interval)
'''

# ------------------------------------------------------------
# 9) Objective: maximize tasks - penalty
# ------------------------------------------------------------
pres_list = [is_present[tid] for tid in task_dict]

late_terms = []
for tid, t in task_dict.items():
    if t["type"] in ("Download", "Remove"):
        late_terms.append((start_of(iv_task[tid]) / float(T_HORIZON)) * is_present[tid])

mdl.add(mdl.maximize(W_TASK * sum(pres_list) - ALPHA_LATE * sum(late_terms)))

#- ALPHA_LATE * sum(late_terms)
# ------------------------------------------------------------
# 10 Solve
# ------------------------------------------------------------
from docplex.cp.model import CpoSolveResult
'''
msol: CpoSolveResult = mdl.solve(LogVerbosity="Terse", TimeLimit=10)
if msol:
    print("Objective value:", msol.get_objective_values())
    for tid, iv in iv_task.items():
        vsol = msol.get_var_solution(iv)
        if vsol is not None and vsol.is_present():
            print(
                f"TID {tid:>4}  type={task_dict[tid]['type']:<10}  "
                f"start={vsol.get_start()}  end={vsol.get_end()}"
            )
else:
    print("No solution found") 
'''
