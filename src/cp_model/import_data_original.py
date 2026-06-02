import openpyxl
import pandas as pd
from collections import defaultdict
from docplex.mp.model import Model
import sys


# 檢查是否有足夠的參數傳入 (避免 index out of range 錯誤)
filename = "cp_small_1.xlsx"
if len(sys.argv) > 1:
    filename = sys.argv[1]      # 接收第一個參數 
else:
    print(f"錯誤：無參數傳入，使用預設檔名 {filename}")
# 這一塊只在「單獨執行此檔案」檢查用，被 import 時不跑

def classify_type(t: str) -> str:
    # 將任務類型字串標準化
    t = t.lower()
    if "shoot" in t:
        return "Shoot"
    if "download" in t:
        return "Download"
    return {
        "remove": "Remove",
        "track": "Track",
        "t maneuver": "T_maneuver",
        "p maneuver": "P_maneuver",
        "h maneuver": "H_maneuver",
    }.get(t, "Other")

    

def load_activity_data(df: pd.DataFrame) -> dict:
    # 處理 activity 表並回傳任務字典與分類 dict
    df["type"] = df["type"].astype(str).str.strip()
    df["group"] = df["group"].fillna(-1).astype(int)
    df["info"] = df["info"].fillna(-1).astype(int)
    df["task_type"] = df["type"].apply(classify_type)

    task_dict = {
        int(row["id"]): {
            "type": row["task_type"],
            "group": int(row["group"]),
            "duration": int(round(row["duration"])),
            "start": pd.to_datetime(row["starttime"]),
            "end": pd.to_datetime(row["endtime"]),
            "memory": int(row["memory"]),
            "scheduled": int(row["scheduled"]),
            "info": int(row["info"]),
        }
        for _, row in df.iterrows()
    }

    P_H_group_cid_tid = defaultdict(list)
    S_D_R_group = defaultdict(list)

    for tid, tinfo in task_dict.items():
        if tinfo["info"] != -1:
            P_H_group_cid_tid[tinfo["info"]].append(tid)
        if tinfo["group"] != -1:
            S_D_R_group[tinfo["group"]].append(tid)

    return task_dict, P_H_group_cid_tid, S_D_R_group


def load_contact_data(df: pd.DataFrame) -> dict:
    # 處理 contact 表並回傳 contact 字典
    for col in ["rise", "fade", "R-typerise", "R-typefade"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["type"] = df["type"].astype(str).str.strip()

    return {
        int(row["id"]): {
            "type": row["type"],
            "rise": row["rise"],
            "fade": row["fade"],
            "R-typerise": row["R-typerise"],
            "R-typefade": row["R-typefade"],
        }
        for _, row in df.iterrows()
    }


def load_eclipse_intervals(df: pd.DataFrame) -> list:
    # 處理 eclipse 表並回傳日蝕區間列表
    df["penumbraentrancetime"] = pd.to_datetime(df["penumbraentrancetime"])
    df["penumbraexittime"] = pd.to_datetime(df["penumbraexittime"])
    df["type"] = df["type"].astype(str).str.strip()

    entry_times = df.loc[df["type"] == "Sun", "penumbraentrancetime"].tolist()
    exit_times = df.loc[df["type"] == "Sun", "penumbraexittime"].tolist()

    intervals = [
        {"start": entry_times[i], "end": entry_times[i + 1]}
        for i in range(len(entry_times) - 1)
    ]
    if entry_times and exit_times:
        intervals.append({"start": entry_times[-1], "end": exit_times[-1]})

    return intervals


def load_data(file_path: str):
    # 主控流程：載入所有資料
    excel_file = pd.ExcelFile(file_path)

    activity_df = excel_file.parse("activity")
    contact_df = excel_file.parse("contact")
    eclipse_df = excel_file.parse("eclipse")
    image_df = excel_file.parse("image")
    task_dict, P_H_group_cid_tid, S_D_R_group = load_activity_data(activity_df)
    contact_dict = load_contact_data(contact_df)
    eclipse_intervals = load_eclipse_intervals(eclipse_df)
    file_value, memory_value = image_df.iloc[0][['file', 'memory']]

    return {
        "task_dict": task_dict,
        "P_H_group_cid_tid": P_H_group_cid_tid,
        "S_D_R_group": S_D_R_group,
        "contact_dict": contact_dict,
        "eclipse_intervals": eclipse_intervals,
        "file": int(file_value),
        "memory": int(memory_value)
    }

_loaded_data = load_data(filename)
contact_dict = _loaded_data["contact_dict"]
eclipse_intervals = _loaded_data["eclipse_intervals"]
task_dict = _loaded_data["task_dict"]
P_H_group_cid_tid = _loaded_data["P_H_group_cid_tid"]
S_D_R_group = _loaded_data["S_D_R_group"]
File_value=_loaded_data["file"]
Memory_value=_loaded_data["memory"]
if __name__ == "__main__":
    data = load_data(filename)
    print(
        f"Loaded {len(data['task_dict'])} tasks, {len(data['contact_dict'])} contacts."
    )
    #print(data['task_dict'])

print(f"{File_value} {Memory_value}")
