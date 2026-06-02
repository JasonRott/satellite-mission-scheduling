import pandas as pd
import subprocess
import os
import time

model_name_set = ['CP', 'MILP']
#model_name_set = ['CP', 'MILP']
timelimits = [30,60,120,180,300,600]
#timelimits = [30]
size_set = ['small', 'medium', 'large']
#size_set = ['medium']

for model_name in model_name_set:
    for size in size_set:
        for timelimit in timelimits:
            #run first test data in size set
            filename = f'{model_name}_{size}_1.xlsx'
            print(f'Running import_data_original.py with file: {filename}')
            # 相當於在終端機執行以下指令：
            subprocess.run([
            "python",           # 執行指令
            "gantt_3rows.py", # 檔案名稱
            filename,         # 參數 1
            str(timelimit),         # 參數 2
            ])
            subprocess.run([
            "python",           # 執行指令
            "gantt_7rows.py", # 檔案名稱
            filename,         # 參數 1
            str(timelimit),         # 參數 2
            ])
        
        for timelimit in timelimits:  
            #run second test data in size set
            filename = f'{model_name}_{size}_2.xlsx'
            print(f'Running import_data_original.py with file: {filename}')
            # 相當於在終端機執行以下指令：
            subprocess.run([
            "python",           # 執行指令
            "gantt_3rows.py", # 檔案名稱
            filename,         # 參數 1
            str(timelimit),         # 參數 2
            ])
            subprocess.run([
            "python",           # 執行指令
            "gantt_7rows.py", # 檔案名稱
            filename,         # 參數 1
            str(timelimit),         # 參數 2
            ])
        
        