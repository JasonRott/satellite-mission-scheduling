import sys

target_filename = "cp_small_1.xlsx"
set_timelimit = 120

# 解析參數：python main_solver.py [filename] [timelimit]
if len(sys.argv) > 1:
    # 第一個參數通常是檔名 (這會被 import_data_original 自動讀取到，因為 sys.argv 是共享的)
    target_filename = sys.argv[1]

if len(sys.argv) > 2:
    # 第二個參數是時間限制
    set_timelimit = float(sys.argv[2])

filename_detail = target_filename.split(".xlsx")[0].split("_")
print(f"{filename_detail[1]}_{filename_detail[2]}" )

# -*- coding: utf-8 -*-
import os
import pandas as pd
from docplex.cp.model import CpoSolveResult

import import_data_original as data
import cpo_model_original  as cp
print(f"---Solving CP model for file: {target_filename} with timelimit: {set_timelimit} seconds---")

# Solve CP model
msol: CpoSolveResult = cp.mdl.solve(LogVerbosity="Terse", TimeLimit=set_timelimit)


results = []
total_start_time = cp.total_start_time
task_dict = cp.task_dict
contact_dict = cp.contact_dict
eclipse_intervals = cp.eclipse_intervals
z_download_interval = cp.z_download_interval

filename = data.filename

for tid, tinfo in task_dict.items():
    iv = cp.iv_task[tid]
    vsol = msol.get_var_solution(iv) if msol else None
    present = 1 if (vsol is not None and vsol.is_present()) else 0

    if present:
        st = vsol.get_start()  # seconds from total_start_time
        en = vsol.get_end()
        real_start = total_start_time + pd.to_timedelta(st, unit="s")
        real_end = total_start_time + pd.to_timedelta(en, unit="s")
    else:
        real_start = None
        real_end = None

    contact_id = None
    if present and tinfo["type"] == "Download":
        copies = cp._dl_copies.get(tid, {})
        for cid, ivc in copies.items():
            v = msol.get_var_solution(ivc)
            if v is not None and v.is_present():
                contact_id = cid
                break
    elif present and tinfo["type"] == "Track":
        copies = cp._tr_copies.get(tid, {})
        for cid, ivc in copies.items():
            v = msol.get_var_solution(ivc)
            if v is not None and v.is_present():
                contact_id = cid
                break
    z_eclipse = None
    grp = " " if tinfo.get("group", -1) == -1 else tinfo["group"]
    if tinfo["type"] == "Download": 
        for i, interval in enumerate(eclipse_intervals):
            interval_var = z_download_interval[tid][i]
            if msol.get_value(interval_var) == 1:
                z_eclipse = i
                break
    results.append(
        {
            "task_id": tid,
            "contact_id": contact_id,
            "start_time": real_start,
            "end_time": real_end,
            "scheduled": present,
            "group": grp,
            "type": tinfo["type"],
            "duration": tinfo["duration"] if tinfo["type"]=="Download" else 0,
            "z_eclipse": z_eclipse if tinfo["type"]=="Download" else 0,
        }
    )

result_df = pd.DataFrame(results).sort_values(by="task_id")
schedule_df = result_df.sort_values(
    by=["scheduled", "start_time", "task_id"], ascending=[False, True, True]
)
results2=results.copy()
for i, interval in enumerate(eclipse_intervals):
    results2.append(
        {
            "task_id": 0,
            "contact_id": f"eclipse_{i}",
            "start_time": interval["start"],
            "end_time": interval["end"],
            "scheduled": 1,
            "group": 0,
            "type": "eclipse",
        } 
    )        
#schedule_df2 = pd.DataFrame(results2).sort_values(
#    by=["scheduled", "start_time", "task_id"], ascending=[False, True, True]
#)
# Output to Excel: data2.xlsx, replacing 'result' and 'schedule' sheets if file exists
out_path = filename
mode = "a" if os.path.exists(out_path) else "w"
with pd.ExcelWriter(
    out_path, engine="openpyxl", mode=mode, if_sheet_exists="replace"
) as writer:
    result_df.to_excel(writer, sheet_name="result", index=False)
    schedule_df.to_excel(writer, sheet_name=f"schedule_{set_timelimit}", index=False)
    #schedule_df2.to_excel(writer, sheet_name="schedule_with_eclipse", index=False)
    print("Wrote:", out_path)

import pandas as pd

# 確保有找到解 (CPO 沒解時 solution 可能為 None 或狀態為 False)
if msol:
    # --- (A) 取得 Objective Value ---
    # CP 中使用 get_objective_value()
    obj_value = msol.get_objective_value()

    # --- (B) 取得統計資訊 ---
    # CP 的 solution 物件直接包含這些資訊，不用找 mdl.solve_details
    # 註：CP 的 "Gap" 定義可能與 MIP 不同，通常是 get_objective_gap()
    gap = msol.get_objective_gap()
    
    # 取得求解時間
    solve_time = msol.get_solve_time()

    # --- (C) 計算變數為 1 的數量 ---
    # CP 的變數值通常是整數，但用 get_value() 取值邏輯是一樣的
    x_task_count = sum(1 for var in cp.iv_task.values() if msol.get_var_solution(var).is_present())

    # --- (D) 取得迭代/分支資訊 ---
    # CP 沒有 "Iterations" (單純形法迭代)，對應的概念是 "Failures" 或 "Branches" (搜尋樹節點)
    # 我們可以透過 get_solver_infos() 取得更多細節
    solver_infos = msol.get_solver_infos()
    num_branches = solver_infos.get("NumberOfBranches", 0) # 或是 "NumberOfFails"

    # --- 打包回傳資料 ---
    result_data = {
        "filename": filename,
        "timelimit": set_timelimit,
        "status": msol.get_solve_status(),  # 例如 'Optimal', 'Feasible'
        "objective": obj_value,
        "gap": gap,
        "solve_time": solve_time,
        "scheduled_count": x_task_count,
        "branches": num_branches, # 取代原本的 iterations
    }

else:
    # 無解的情況
    result_data = {
        "filename": filename,
        "timelimit": set_timelimit,
        "status": "No Solution",
        "objective": None,
        "gap": None,
        "solve_time": None,
        "scheduled_count": 0,
        "branches": 0
    }

# 轉成 DataFrame
result_data_df = pd.DataFrame([result_data])

with pd.ExcelWriter(
    "cp_test_timelimit_result.xlsx", engine="openpyxl", mode="a", if_sheet_exists="overlay"
) as writer:
    sheet_name = f"{filename_detail[1]}_{filename_detail[2]}"   
    if sheet_name in writer.sheets:
            # 取得現有的 sheet 物件
            existing_sheet = writer.sheets[sheet_name]
            # max_row 告訴我們目前有資料的最後一行在哪
            start_row = existing_sheet.max_row
            
            # 因為是接著寫，所以不需要標題 (header=False)
            result_data_df.to_excel(
                writer, 
                sheet_name=sheet_name, 
                index=False, 
                header=False, 
                startrow=start_row  # 從最後一行的下一行開始寫 (overlay 會自動往下)
            )
    else:
        # 如果檔案存在，但這個 Sheet 還不存在，就直接寫入 (包含標題)
        result_data_df.to_excel(writer, sheet_name=sheet_name, index=False)

# Calculate Average Start Time Deviation for Download tasks
download_deviations = []
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download" or tinfo["type"] == "Remove":
        iv = cp.iv_task[tid]
        vsol = msol.get_var_solution(iv) if msol else None
        if vsol is not None and vsol.is_present():
            scheduled_sec = vsol.get_start()
            scheduled_start = total_start_time + pd.to_timedelta(scheduled_sec, unit="s")
            planned_start = tinfo["start"]
            deviation = (scheduled_start - planned_start).total_seconds()
            download_deviations.append(abs(deviation)/86400)

if download_deviations:
    avg_deviation = sum(download_deviations) / len(download_deviations)
    print(f"Average Start Time Deviation (Download): {avg_deviation} ")
else:
    print("No Download tasks found for deviation calculation.")
