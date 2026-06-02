import pandas as pd
import subprocess
import os
import time

def check_last_run_is_optimal(excel_path, sheet_name):
    """
    讀取 Excel 的最後一列，檢查 Status 是否為 Optimal
    """
    try:
        # 讀取 Excel (只讀需要的 sheet)
        # 注意：如果檔案很大，頻繁讀取會有點慢，但對於測試來說通常沒問題
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        if df.empty:
            return False
        # 取得最後一筆寫入的資料 (iloc[-1])
        last_row = df.iloc[-1]
        status = str(last_row['status'])  # 轉字串以免它是 NaN 或其他型別

        # 檢查關鍵字 (忽略大小寫)
        if "optimal" in status.lower():
            return True 
        return False
    except Exception as e:
        print(f"  [警告] 讀取 Excel 檢查失敗: {e}")
        return False

model_name = 'cp'
timelimits = [30,60,120,180,300,600]
#timelimits = [str(3+0.1*i) for i in range(20)]
timelimits = [100]
size_set = ['small', 'medium', 'large']
size_set = ['large']

for size in size_set:
    
    for timelimit in timelimits:
        
        #run first test data in size set
        filename = f'{model_name}_{size}_1.xlsx'
        print(f'---Running write_excel_original.py with file: {filename}---')
        # 相當於在終端機執行以下指令：
        subprocess.run([
        "python",           # 執行指令
        "write_excel_original.py", # 檔案名稱
        filename,         # 參數 1
        str(timelimit),         # 參數 2
        ])
        if check_last_run_is_optimal(f"{model_name}_test_timelimit_result.xlsx", f"{size}_1"):
            print(f"---Skipping second test data for {filename} at timelimit {timelimit} since optimal solution was found---")
            break
    
    for timelimit in timelimits:    
        #run second test data in size set
        filename = f'{model_name}_{size}_2.xlsx'
        print(f'---Running write_excel_original.py with file: {filename}---')
        # 相當於在終端機執行以下指令：
        subprocess.run([
        "python",           # 執行指令
        "write_excel_original.py", # 檔案名稱
        filename,         # 參數 1
        str(timelimit),         # 參數 2
        ])
        if check_last_run_is_optimal(f"{model_name}_test_timelimit_result.xlsx", f"{size}_2"):
            print(f"---Skipping second test data for {filename} at timelimit {timelimit} since optimal solution was found---")
            break