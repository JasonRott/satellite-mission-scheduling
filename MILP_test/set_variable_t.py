import import_data_original as data
import openpyxl
import pandas as pd
from collections import defaultdict
from docplex.mp.model import Model
import datetime

def to_sec(dt):  # seconds relative to total_start_time
    return int((dt - total_start_time).total_seconds())
#------------------------------------------------------------
# 建立 dict
#------------------------------------------------------------
contact_dict = data.contact_dict
eclipse_intervals = data.eclipse_intervals
task_dict = data.task_dict
total_start_time = min([_["start"] for _ in task_dict.values()])
total_end_time = max([_["start"] for _ in task_dict.values()]) 
P_H_group_cid_tid = data.P_H_group_cid_tid
S_D_R_group = data.S_D_R_group
File_value=data.File_value
Memory_value=data.Memory_value
M = (total_end_time-total_start_time).total_seconds()+86400
print(M)
M_for_binary = 100
eps = 0.0001
start_time = {}
end_time = {}
overlap = []
possible_R_contacts_by_download = {}
shoot_task_dict = {tid: tinfo for tid, tinfo in task_dict.items() if tinfo["type"] == "Shoot"}
remove_task_dict={tid: tinfo for tid, tinfo in task_dict.items() if tinfo["type"] == "Remove"}
valid_contacts = []
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "P_maneuver":
        if tinfo["info"] != "None":
            valid_contacts.append(tinfo["info"])
#------------------------------------------------------------            
# 建立模型
#------------------------------------------------------------
mdl = Model(name="Satellite Task Scheduling")
# 設定差距為 0.01 (1%)，也就是說，當找到的解與理論最佳解的差距在 1% 以內時，就停止求解
#mdl.parameters.mip.tolerances.mipgap = 0.01
mdl.parameters.timelimit =300

total_start_time = min(t["start"] for t in task_dict.values())

T_HORIZON = max(
    int((t["start"] - total_start_time).total_seconds()) for t in task_dict.values() 
) + 86400
#------------------------------------------------------------
# 建立二元變數：是否執行該任務
#------------------------------------------------------------
x_task = {tid: mdl.binary_var(name=f"x_task_{tid}") for tid in task_dict}
#------------------------------------------------------------            
#其他變數
#------------------------------------------------------------
z_download_interval = {}
z_shoot_interval = {}
z_to_dict = {}
z_tc = {}
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download":
        start_var = mdl.continuous_var(lb=0, name=f"start_{tid}")
        start_time[tid] = start_var
        z_download_interval[tid] = {}
        mdl.add_constraint(start_time[tid]<=M * (x_task[tid]) + eps, f"fix_start_if_not_scheduled_{tid}")
        #mdl.add_constraint(start_time[tid] + M * (x_task[tid]) + eps >= M, f"fix_start_if_not_scheduled_{tid}")
        for i, interval in enumerate(eclipse_intervals):
            z_download_interval[tid][i] = mdl.binary_var(name=f"z_download_{tid}_{i}")

    if tinfo["type"] == "Remove":
        # 起訖時間變數（轉為 float，以秒為單位）
        start_var = mdl.continuous_var(lb=0, name=f"start_{tid}")
        start_time[tid] = start_var
        mdl.add_constraint(start_time[tid]<=M * (x_task[tid]) + eps, f"fix_start_if_not_scheduled_{tid}")
        #mdl.add_constraint(start_time[tid] + M * (x_task[tid]) + eps >= M, f"fix_start_if_not_scheduled_{tid}")
        
    if tinfo["type"] == "Shoot":
        z_shoot_interval[tid] = {}
        for i, interval in enumerate(eclipse_intervals):
            z_shoot_interval[tid][i] = mdl.binary_var(name=f"z_shoot_{tid}_{i}")

# ------------------------------------------------------------
#限制式
# ------------------------------------------------------------
for tid, tinfo in task_dict.items():
    overlap = []
    if tinfo["type"] == "Track":

        # 1 Track 需在J type地面站 接觸時間
        t_start = tinfo["start"]
        t_end = tinfo["end"]
        possible_contacts = []
        for cid, c in contact_dict.items():
            c_start = c["rise"]
            c_end = c["fade"]
            is_overlap = t_end <= c_end and t_start >= c_start
            if is_overlap:
                if c["type"].startswith("R"):
                    continue
                possible_contacts.append(cid)
        # possible_contacts:track 可能J type 地面站候選人
        z_track_tc = {}
        for cid in possible_contacts:
            z_track_tc[cid] = mdl.binary_var(name=f"z_track_{tid}_{cid}")
        mdl.add_constraint(
            mdl.sum(z_track_tc[cid] for cid in possible_contacts) == x_task[tid],
            f"contact_assignment_{tid}",
        )
        # 2 Track no overlap
       
        z_Tr = {}
        for other_id, other_info in task_dict.items():
            if other_id != tid and other_info["type"] == "Track":
                    z_Tr[other_id] = mdl.binary_var(name=f"z_tr_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        (t_start - total_start_time).total_seconds()
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_Tr[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= (t_end - total_start_time).total_seconds()
                        - M * z_Tr[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )
    elif tinfo["type"] == "Shoot":
        t_start = tinfo["start"]
        t_end = tinfo["end"]
        z_Shoot = {}
        for other_id, other_info in task_dict.items():
            if other_id in overlap:
                continue
            if other_id != tid:
                if other_info["type"] == "Shoot":
                    z_Shoot[other_id] = mdl.binary_var(name=f"z_sh_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        (t_start - total_start_time).total_seconds()
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_Shoot[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]),
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= (t_end - total_start_time).total_seconds()
                        - M * z_Shoot[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]),
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )

    elif tinfo["type"] == "Download":
        overlap.append(tid)
        # Download 起訖時間範圍限制
        # 時間窗
        earliest = tinfo["start"]
        latest = tinfo["end"]
        duration = tinfo["duration"]
        # 限制排入允許時間窗（相對 earliest 的秒數）
        mdl.add_constraint(
            start_time[tid]
            >= x_task[tid] * (earliest - total_start_time).total_seconds() - eps,
            f"start_lb_{tid}",
        )
        mdl.add_constraint(
            start_time[tid] + duration
            <= (latest - total_start_time).total_seconds() + (1 - x_task[tid]) * M + eps,
            f"end_ub_{tid}",
        )
        
        # shoot執行 download才能執行"""10-9"""
        mdl.add_constraint(
            x_task[S_D_R_group[tinfo["group"]][0]] >= x_task[tid], f"Download_9_{tid}"
        )
        
        # Download 需在R type地面站 接觸時間
        z_tc[tid] = {}
        possible_R_contacts = [
            cid
            for cid, c in contact_dict.items()
            if c["type"] == "R-type"
            and pd.notnull(c["R-typerise"])
            and pd.notnull(c["R-typefade"])
            and c["R-typerise"] <= latest
            and c["R-typefade"] >= earliest
            and (cid in valid_contacts)
        ]
        possible_R_contacts_by_download[tid] = possible_R_contacts
        # 對每個 contact 建立是否選擇的變數 z_tc
        for cid in possible_R_contacts:
             z_tc[tid][cid] = mdl.binary_var(name=f"z_{tid}_{cid}")
        # 最多只能選一個 contact
        mdl.add_constraint(
            mdl.sum(z_tc[tid][cid] for cid in possible_R_contacts) == x_task[tid],
            f"contact_assignment_{tid}",
        )
        
        # 若使用某個 contact，則其對應的 P, H 任務也要執行
        for cid in possible_R_contacts:
            if cid not in P_H_group_cid_tid:
                continue
            p = P_H_group_cid_tid[cid][0]
            h = P_H_group_cid_tid[cid][1]
            """10-10"""
            mdl.add_constraint(
                x_task[p] + x_task[h] >= 2 - (1 - z_tc[tid][cid]) * M_for_binary, f"Dowload_10-1"
            )

            mdl.add_constraint(
                start_time[tid]
                >= z_tc[tid][cid] * (task_dict[p]["end"] - total_start_time).total_seconds() - eps,
                f"Dowload_10-2-3",
            )
            mdl.add_constraint(
                start_time[tid] + duration
                <= (task_dict[h]["start"] - total_start_time).total_seconds()
                + (1 - z_tc[tid][cid]) * M + eps,
                f"Dowload_10-2-2",
            )
        
        #print(possible_R_contacts)
        
        """10-8"""
        for cid in possible_R_contacts:
            c = contact_dict[cid]
            c_start = c["R-typerise"]
            c_end = c["R-typefade"]

            mdl.add_constraint(
                start_time[tid]
                >= z_tc[tid][cid] * (c_start - total_start_time).total_seconds() - eps,
                f"Rtyperise_lb_{tid}_{cid}",
            )
            mdl.add_constraint(
                start_time[tid] + duration
                <= (c_end - total_start_time).total_seconds() + (1 - z_tc[tid][cid]) * M + eps,
                f"Rtypefade_ub_{tid}_{cid}",
            )
        
        z_to = {}
        for other_id, other_info in task_dict.items():
            """10-1,10-6"""
            if other_id in overlap:
                continue
            if other_info["type"] in ("Download"):
                if other_id == tid:
                    continue
                
                z_to[other_id] = mdl.binary_var(name=f"z_{tid}_{other_id}")

                
                # Constraint 1: tid starts after other ends
                mdl.add_constraint(
                    start_time[tid]
                    >= start_time[other_id] + other_info["duration"]
                    - M * (1 - z_to[other_id])- M * (2 - x_task[tid] - x_task[other_id]) - eps,
                    f"dl_no_overlap_1_{tid}_{other_id})",
                )

                # Constraint 2 (flipped): other starts after tid ends
                mdl.add_constraint(
                    start_time[other_id]
                    >=  start_time[tid] + duration - M * (z_to[other_id]) - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                    f"dl_no_overlap_2_{tid}_{other_id})",
                )
                
            """10-2,3,4,5"""
            if other_info["type"] in (
                "T_maneuver",
                "H_maneuver",
                "P_maneuver",
                "Shoot",
            ):
                if not (
                    tinfo["end"] <= other_info["start"]
                    or tinfo["start"] >= other_info["end"]
                ):

                    z_to[other_id] = mdl.binary_var(name=f"z_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        start_time[tid]
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_to[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= start_time[tid]
                        + duration
                        - M * z_to[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )
        z_to_dict[tid] = z_to
        
    elif tinfo["type"] == "Remove":

        # Remove 起訖時間範圍限制
        # 時間窗
        earliest = tinfo["start"]
        latest = tinfo["end"]
        duration = tinfo["duration"]
        
        # 限制排入允許時間窗（相對 earliest 的秒數）
        mdl.add_constraint(
            start_time[tid] >= x_task[tid]*(earliest - total_start_time).total_seconds() - eps,
            f"start_lb_{tid}",
        )
        mdl.add_constraint(
            start_time[tid] + duration <= (latest - total_start_time).total_seconds() + M*(1-x_task[tid]) + eps,
            f"end_ub_{tid}",
        )
        
        # 6 必須先執行同 group 的 Shoot 才能執行 Remove
        mdl.add_constraint(
            x_task[S_D_R_group[tinfo["group"]][0]] == x_task[tid], f"Download_9_{tid}"
        )
        
        grp_id = tinfo["group"]  # 目前這顆 Remove 所屬 group
        
        # ---------- 與同組 Shoot 的規則 1、3 ----------
        for sid, sinfo in task_dict.items():
            if sinfo["type"] != "Shoot" or sinfo["group"] != grp_id:
                continue

            shoot_end_sec = (sinfo["end"] - total_start_time).total_seconds()

            # 規則 1＋3：Remove 等 Shoot 結束；且不能重疊
            mdl.add_constraint(
                start_time[tid] >= shoot_end_sec - M * (1 - x_task[sid]) - eps,
                f"R_after_Shoot_{tid}_{sid}",
            )
        
        # ---------- 與同組 Download 的規則 2 ----------
        
        # 找到同組的 Download 任務
        for did, dinfo in task_dict.items():
            if dinfo["type"] == "Download" and dinfo["group"] == grp_id:
                # 直接從字典中取得可能的 R-type 地面站
                if did in possible_R_contacts_by_download:
                    for cid in possible_R_contacts_by_download[did]:
                        c = contact_dict[cid]
                        r_fade_time = (c["R-typefade"] - total_start_time).total_seconds()
                        
                        # 建立 if_then 約束，關聯 Remove 和 Download
                        mdl.add_constraint(
                                start_time[tid] >= r_fade_time + 6 -M * (1 - z_tc[did][cid]) - eps
                        )
       
        # ----------  Remove 4,5 不重疊 ----------
        
        for did, dinfo in task_dict.items():
            if dinfo["type"] not in ("Download", "Remove"):
                continue
            if did == tid:
                continue
            d_start = start_time[did]
            d_end = d_start + dinfo["duration"]

            z_RDx = mdl.binary_var(name=f"y_RDx_{tid}_{did}")

            mdl.add_constraint(
                start_time[tid] + duration
                <= d_start + M * z_RDx + M * (2 - x_task[tid] - x_task[did]) + eps,
                f"R_before_Dx_{tid}_{did}",
            )
            mdl.add_constraint(
                start_time[tid]
                >= d_end - M * (1 - z_RDx) - M * (2 - x_task[tid] - x_task[did]) - eps,
                f"R_after_Dx_{tid}_{did}",
            )
        
    elif tinfo["type"] == "T_maneuver":
        t_start = tinfo["start"]
        t_end = tinfo["end"]
        # T manuever no overlap\

        z_T = {}
        for other_id, other_info in task_dict.items():
            if other_id != tid:
                if (
                    other_info["type"] == "T_maneuver"
                    or other_info["type"] == "H_maneuver"
                    or other_info["type"] == "P_maneuver"
                    or other_info["type"] == "Shoot"
                ):
                    z_T[other_id] = mdl.binary_var(name=f"z_tman_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        (t_start - total_start_time).total_seconds()
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_T[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= (t_end - total_start_time).total_seconds()
                        - M * z_T[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )

    elif tinfo["type"] == "P_maneuver":
        t_start = tinfo["start"]
        t_end = tinfo["end"]
        z_P = {}
        for other_id, other_info in task_dict.items():
            if other_id != tid:
                if (
                    other_info["type"] == "H_maneuver"
                    or other_info["type"] == "P_maneuver"
                    or other_info["type"] == "Shoot"
                ):
                    z_P[other_id] = mdl.binary_var(name=f"z_pman_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        (t_start - total_start_time).total_seconds()
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_P[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= (t_end - total_start_time).total_seconds()
                        - M * z_P[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )
    elif tinfo["type"] == "H_maneuver":
        t_start = tinfo["start"]
        t_end = tinfo["end"]
        z_H = {}
        for other_id, other_info in task_dict.items():
            if other_id != tid:
                if other_info["type"] == "H_maneuver" or other_info["type"] == "Shoot":
                    z_H[other_id] = mdl.binary_var(name=f"z_hman_{tid}_{other_id}")
                    other_start = other_info["start"]
                    other_end = other_info["end"]

                    mdl.add_constraint(
                        (t_start - total_start_time).total_seconds()
                        >= (other_end - total_start_time).total_seconds()
                        - M * (1 - z_H[other_id])
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{tid}>=e{other_id}-M*(1-z)-M*(2-x{tid}-x{other_id})",
                    )

                    mdl.add_constraint(
                        (other_start - total_start_time).total_seconds()
                        >= (t_end - total_start_time).total_seconds()
                        - M * z_H[other_id]
                        - M * (2 - x_task[tid] - x_task[other_id]) - eps,
                        f"S{other_id}>=e{tid}-M*z-M*(2-x{tid}-x{other_id})",
                    )
#  ------------------------------------------------------------
#  P, H 必須同時執行
# ------------------------------------------------------------                    
for group_id, (tid_H, tid_P) in P_H_group_cid_tid.items():
    mdl.add_constraint(x_task[tid_H] == x_task[tid_P], f"H_P_6_{group_id}")
# ------------------------------------------------------------
#  Eclipse: limit shooting and download time during eclipse
# -----------------------------------------------------------

for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download":
        duration = tinfo["duration"]
        
        # 只能選一個 interval OR 不做這個任務
        mdl.add_constraint(
            mdl.sum(z_download_interval[tid][i] for i in range(len(eclipse_intervals))) == x_task[tid]
        )

        # 關閉所有未選擇 interval 的限制
        for i, interval in enumerate(eclipse_intervals):
            Si = to_sec(interval["start"])
            Ei = to_sec(interval["end"])

            mdl.add_indicator(
                z_download_interval[tid][i],   # If z_i == 1
                start_time[tid] >= Si
            )

            mdl.add_indicator(
                z_download_interval[tid][i],
                start_time[tid] + duration <= Ei
            )
        

for i, interval in enumerate(eclipse_intervals):
    mdl.add_constraint(
        mdl.sum(
            [z_download_interval[tid][i] * tinfo["duration"]
            for tid, tinfo in task_dict.items()
            if tinfo["type"] == "Download"]
        )
        <= 600,
        f"download_7-3_sum_of_eclipse_intervals_{i}_downloadtime<=10_min",
    )

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
        mdl.add_constraint(
            mdl.sum(
                x_task[tid] * task_dict[tid]["duration"]
                for tid in shoot_tids_in_interval
            )
            <= 480,
            f"shoot_eclipse_interval_{i}_max_8min",
        )

#------------------------------------------------------------
#  Memory and File interval building
# ------------------------------------------------------------

shoot_start_times = []
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Shoot":
            shoot_start_times.append((tinfo["end"] - total_start_time).total_seconds())
shoot_start_times = sorted(set(shoot_start_times))
memory_intervals = [{"start":shoot_start_times[i],"end": shoot_start_times[i+1]}
                for i in range(len(shoot_start_times)-1)]
max_end = max(
    (tinfo["end"] - total_start_time).total_seconds()
    for tinfo in task_dict.values()
)
if shoot_start_times:
    memory_intervals.append({"start":shoot_start_times[-1],"end": M})
#print(memory_intervals)
shoot_to_interval = {}

for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Shoot":
        st = (tinfo["end"] - total_start_time).total_seconds()
        for i, interval in enumerate(memory_intervals):
            if interval["start"] <= st < interval["end"]:
                shoot_to_interval[tid] = i
                break

z_memory_interval={}
for tid, tinfo in remove_task_dict.items():
    z_memory_interval[tid] = {}
    for i, interval in enumerate(memory_intervals):
        z_memory_interval[tid][i] = mdl.binary_var(name=f"z_memory_{tid}_{i}")
# ------------------------------------------------------------
#  Memory and File capacity constraints
# ------------------------------------------------------------
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Remove":
        duration = tinfo["duration"]
        mdl.add_constraint(
            mdl.sum(z_memory_interval[tid][j] for j in range(len(memory_intervals))) == x_task[tid],
            f"memory_sum",
        )
        for i, interval in enumerate(memory_intervals):
            mdl.add_constraint(
                start_time[tid]
                >= interval["start"]-(1- z_memory_interval[tid][i])*M,
                f"memory_lb_{tid}_{i}",
            )
            mdl.add_constraint(
                start_time[tid] + duration
                <= interval["end"] 
                + (1 - z_memory_interval[tid][i]) * M,
                f"memory_ub_{tid}_{i}",
            )

for tid, tinfo in shoot_task_dict.items():       
        before_shoot_mem=sum( [x_task[other_id]*other_info["memory"] for other_id, other_info in shoot_task_dict.items()  if shoot_to_interval[other_id]< shoot_to_interval[tid]])

        before_remove_mem= sum( [task_dict[S_D_R_group[other_info["group"]][0]]["memory"]*z_memory_interval[other_id][i]   for other_id, other_info in remove_task_dict.items() for i, interval in enumerate(memory_intervals) if i< shoot_to_interval[tid]]
        )
        mdl.add_constraint( x_task[tid]*tinfo["memory"]<=
                Memory_value - before_shoot_mem + before_remove_mem 
                ,f"Mem{tid}"                         
        )
        
        before_shoot_file=sum( [x_task[other_id]*5 for other_id, other_info in shoot_task_dict.items()  if shoot_to_interval[other_id]< shoot_to_interval[tid]]
        )

        before_remove_file= sum( [5*z_memory_interval[other_id][i]  for other_id, other_info in remove_task_dict.items() for i, interval in enumerate(memory_intervals) if i< shoot_to_interval[tid]]
        )
        mdl.add_constraint( x_task[tid]*5<=
                File_value - before_shoot_file + before_remove_file
                ,f"File{tid}"                         
        )



# ------------------------------------------------------------
#  目標式
# ------------------------------------------------------------
late_list = []

for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download" or tinfo["type"] == "Remove":
        late_list.append(start_time[tid])

task_list = [x_task[tid] for tid in task_dict]
mdl.maximize(600*mdl.sum(task_list) - 100*(mdl.sum(late_list))/T_HORIZON) 
#- (mdl.sum(late_list))



'''
for c in mdl.iter_binary_vars():
    if "x_task_" in str(c.name):
        print(c, solution.get_value(c))
'''
    #print(c, c.is_satisfied(solution))
#for c in mdl.iter_constraints():
    #print(c)