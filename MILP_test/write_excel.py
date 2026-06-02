import sys

target_filename = "milp_large_1.xlsx"
set_timelimit = 120

# 解析參數：python main_solver.py [filename] [timelimit]
if len(sys.argv) > 1:
    # 第一個參數通常是檔名 (這會被 import_data_original 自動讀取到，因為 sys.argv 是共享的)
    target_filename = sys.argv[1]

if len(sys.argv) > 2:
    # 第二個參數是時間限制
    set_timelimit = int(sys.argv[2])

filename_detail = target_filename.split(".xlsx")[0].split("_")
print(f"{filename_detail[1]}_{filename_detail[2]}" )
import import_data_original as data
import openpyxl
import pandas as pd
from collections import defaultdict
from docplex.mp.model import Model
import datetime
import set_variable_t as set


contact_dict = data.contact_dict
eclipse_intervals = data.eclipse_intervals
task_dict = data.task_dict
total_start_time = min([_["start"] for _ in task_dict.values()])
P_H_group_cid_tid = data.P_H_group_cid_tid
S_D_R_group = data.S_D_R_group 

filename = data.filename
print(f"--- Start Solving: {filename} with Limit: {set_timelimit}s ---")
mdl = set.mdl
mdl.parameters.timelimit = int(set_timelimit)
#mdl.parameters.mip.tolerances.mipgap = 0.05
solution = mdl.solve(log_output=True)
print(mdl.get_solve_status())
if solution is None:
    mdl.export_as_lp("model.lp")

    # 拿到底層 CPLEX engine
    cpx = mdl.get_engine().get_cplex()

    # --- 產生 IIS（舊版 CPLEX 寫法）---
    cpx.conflict.refine()

    # --- 輸出 IIS ---
    cpx.conflict.write("conflict.ilp")
    # compute IIS

x_task = set.x_task
start_time = set.start_time

#solution.display()
from validate_solution import validate_solution

has_conflict = validate_solution(
    solution, task_dict, start_time, x_task, total_start_time
)

if has_conflict:
    print("Conflict exist")
else:
    print("No conflict")

#print(mdl.solve_details)
#print(f"Objective value: {solution.objective_value}")


# Step 1: 擷取解
results = []
grp = " "
for tid, tinfo in task_dict.items():
    exec_flag = float(solution.get_value(x_task[tid]))  # 是否被排入

    if exec_flag >= 0.95:
        if tid in start_time:
            start_sec = solution.get_value(start_time[tid])
            real_start = total_start_time + pd.to_timedelta(start_sec, unit="s")
            end = real_start + pd.to_timedelta(tinfo["duration"], unit="s")
        else:
            real_start = tinfo["start"]
            end = tinfo["end"]
    else:
        real_start = None
        end = None
        # 預設 contact_id 為 None
    contact_id = None

    if tinfo["type"] in ("Download", "Track"):
        for cid in contact_dict:
            var_name = f"z_{tid}_{cid}"
            var = mdl.get_var_by_name(var_name)   # 這是 O(1) 查表，速度快很多
            if var is not None and int(solution.get_value(var)) == 1:
                contact_id = cid
                break

    if tinfo["group"] == -1:
        grp = " "
    else:
        grp = tinfo["group"]
    results.append(
        {
            "task_id": tid,
            "contact_id": contact_id,
            "start_time": real_start,
            "end_time": end,
            "scheduled": exec_flag,
            "group": grp,
            "info": tinfo["info"],
            "type": tinfo["type"],
        }
    )

# Step 2: 建 DataFrame
result_df = pd.DataFrame(results)
result_df = result_df.sort_values(by="task_id")

schedule_df = result_df.sort_values(by="start_time")
'''
parameters = {
    "Filename": target_filename,
    "Solver Objective": solution.objective_value,
    "Solver Status": str(mdl.get_solve_status()),
    "Time Limit (s)": set_timelimit
}
params_df = pd.DataFrame(list(parameters.items()), columns=["Parameter", "Value"])
'''
if solution:
    obj_value = solution.objective_value

    solve_details = mdl.solve_details

    x_task_count = sum(1 for var in x_task.values() if solution.get_value(var) > 0.9)
    
    # 如果你還有其他變數 (例如 z 變數代表接觸)，也可以這樣算：
    # z_count = sum(1 for var in z_vars.values() if solution.get_value(var) > 0.9)

    # --- 打包要回傳的資料 ---
    result_data = {
        "filename": filename,
        "timelimit": set_timelimit,
        "status": str(mdl.get_solve_status()), # 例如 'OPTIMAL_SOLUTION'
        "objective": obj_value,
        "gap": solve_details.mip_relative_gap,
        "solve_time": solve_details.time,
        "scheduled_count": x_task_count,
        "iterations": mdl.solve_details.nb_iterations,
    }

result_data_df = pd.DataFrame([result_data])

# Step 3: 寫入 Excel 中 result 工作表
with pd.ExcelWriter(
    filename, engine="openpyxl", mode="a", if_sheet_exists="replace"
) as writer:
    #result_df.to_excel(writer, sheet_name="result", index=False)
    schedule_df.to_excel(writer, sheet_name=f"schedule_{set_timelimit}", index=False)
    #params_df.to_excel(writer, sheet_name="parameters", index=False)

with pd.ExcelWriter(
    "milp_test_timelimit_result.xlsx", engine="openpyxl", mode="a", if_sheet_exists="overlay"
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
    # 只看 Download / Remove 任務
    if tinfo["type"] == "Download" or tinfo["type"] == "Remove":

        # 若有執行決策變數 x_task，則先看有沒有被排入
        exec_flag = 0.0
        if tid in x_task:
            exec_flag = solution.get_value(x_task[tid])

        if exec_flag >= 0.95:
            # 確保這個任務有對應的 start_time 變數
            if tid in start_time:
                scheduled_sec = solution.get_value(start_time[tid])  # 以秒為單位
                scheduled_start = total_start_time + pd.to_timedelta(scheduled_sec, unit="s")

                planned_start = tinfo["start"]  # 原先規劃開始時間 (Timestamp)

                deviation = (scheduled_start - planned_start).total_seconds()
                # 換成「天」的絕對偏差，跟你原本 /86400 一樣
                download_deviations.append(abs(deviation) / 86400.0)

if download_deviations:
    avg_deviation = sum(download_deviations) / len(download_deviations)
    print(f"Average Start Time Deviation (Download): {avg_deviation}")
else:
    print("No Download tasks found for deviation calculation.")


'''
for tid, tinfo in task_dict.items():
    if tinfo["type"] == "Download" or tinfo['type']=="Remove":
        print(f"{start_time[tid].solution_value}")

solution_x = []
solution_start_time = []
for tid, tinfo in task_dict.items():
    solution_x.append(solution.get_value(x_task[tid]))
    if tinfo["type"] == "Download" or tinfo['type']=="Remove":
        solution_start_time.append(solution.get_value(start_time[tid]))

print("Solver Objective:", solution.get_objective_value())
'''