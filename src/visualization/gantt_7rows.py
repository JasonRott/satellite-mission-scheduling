import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

# --- 1. 資料讀取與準備 ---=
target_filename = "milp_medium_1.xlsx"
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
file_path = f"{filename_detail[0]}_data/{target_filename}" # 您的檔案路徑
try:
    df = pd.read_excel(file_path, sheet_name=f"schedule_{set_timelimit}")
except FileNotFoundError:
    print(f"錯誤：找不到檔案 '{file_path}'。請檢查路徑是否正確。")
    # 如果找不到檔案，您需要自行確認資料讀取步驟成功。
    # 這裡假設讀取成功，開始處理資料

# 確保 'start_time' 欄位是日期時間格式，並處理潛在的空值
df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
df = df.dropna(subset=['start_time']).copy()

# --- 2. 確定任務順序與繪圖參數 ---

# 1. 根據實際的 'start_time' 對所有任務進行排序，建立全局順序
df.sort_values(by='start_time', inplace=True)

# 2. 每個任務的繪圖起點 (X 軸位置) 是它在排序後的索引
df['Plot_Start'] = np.arange(len(df))

# 3. 每個任務的長度固定為 1 (佔橫軸一格)
df['Plot_Duration'] = 1

# 4. 準備 Y 軸 (類型 type) 的分類對應
task_types = df['type'].unique()
custom_order = [
    'T_maneuver', 
    'Remove', 
    'H_maneuver', 
    'Download', 
    'P_maneuver', 
    'Shoot', 
    'Track'
]
# 將 type 映射到一個數值索引，方便繪圖
type_map = {name: i for i, name in enumerate(custom_order)}

# 映射 'type' 欄位到 Y 軸數值位置
df['Y_Position'] = df['type'].map(type_map)

# 5. 準備 Group 的顏色 (如果 'group' 欄位有值，用於視覺區分)
# 填充 group 欄位的空值（NaN）為 0，方便分配顏色
df['group'] = pd.to_numeric(df['group'], errors='coerce') # 步驟 B：將無效值轉為 NaN
df['group'] = df['group'].fillna(0).astype(int)
group_names = sorted(df['group'].unique())
num_groups = len(group_names)

# 選擇一個調色盤
cmap = plt.cm.get_cmap('viridis', num_groups)
group_colors = {g: cmap(i) for i, g in enumerate(group_names)}

# --- 3. 繪製圖表 ---

# 圖表高度根據類型數量決定，以確保清晰
fig, ax = plt.subplots(figsize=(15, max(6, len(task_types) * 0.75)))

# 依據 'group' 繪製條形，給予不同的顏色
for group_val, color in group_colors.items():
    subset = df[df['group'] == group_val]
    if group_val == 0:
        # **設定：沒有 group 的任務，顏色為白色**
        color = 'white'
    ax.barh(
        y=subset['Y_Position'],
        width=subset['Plot_Duration'],
        left=subset['Plot_Start'],
        height=0.7,
        color=color,
        # --- 框線設定 ---
        edgecolor='black', # 框線顏色
        linewidth=0.8      # 框線粗細
    )
    



# 設定 Y 軸標籤為任務類型
y_ticks_indices = np.arange(len(custom_order))
ax.set_yticks(y_ticks_indices)
ax.set_yticklabels(custom_order) # Y 軸標籤使用自定義的文字列表

# 設定 X 軸刻度以顯示每個順序步驟的格子
max_step = df['Plot_Start'].max() + df['Plot_Duration'].max()
ax.set_xticks(np.arange(0, max_step + 1, 10)) # 每隔 10 個步驟顯示一個刻度
ax.grid(axis='x', linestyle='--', alpha=0.5)

# 標記軸和標題
ax.set_title(f'Task Type vs. Sequential Steps\nModel: {filename_detail[0]}, Data: {filename_detail[1]}_{filename_detail[2]}, Timelimit: {set_timelimit}', fontsize=16)
ax.set_xlabel('Task Sequential Steps', fontsize=12)
ax.set_ylabel('Task Type', fontsize=12)

# 調整佈局
plt.tight_layout()

# 儲存圖片
save_path = f'{filename_detail[0]}_gantt/7_rows/{filename_detail[1]}_{filename_detail[2]}/{filename_detail[1]}_{filename_detail[2]}_{filename_detail[0]}_{set_timelimit}_7rows_gantt_chart.png'
plt.savefig(f'{save_path}')
print(f"{save_path} 儲存成功。")