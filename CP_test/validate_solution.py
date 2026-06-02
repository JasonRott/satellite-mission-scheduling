from collections import defaultdict
import pandas as pd


def validate_solution(solution, task_dict, start_time, x_task, total_start_time):
    download_schedule = []
    remove_schedule = []
    shoot_schedule = []
    else_schedule = []

    for tid, tinfo in task_dict.items():
        if int(solution.get_value(x_task[tid])) == 1:
            start_sec = (
                solution.get_value(start_time[tid]) if tid in start_time else None
            )
            if start_sec is None:
                continue
            start_dt = total_start_time + pd.to_timedelta(start_sec, unit="s")
            end_dt = start_dt + pd.to_timedelta(tinfo["duration"], unit="s")

            if tinfo["type"] == "Download":
                download_schedule.append((tid, start_dt, end_dt))
            elif tinfo["type"] == "Remove":
                remove_schedule.append((tid, start_dt, end_dt))
            elif tinfo["type"] == "Shoot":
                shoot_schedule.append((tid, tinfo["start"], tinfo["end"]))
            else:
                else_schedule.append((tid, tinfo["start"], tinfo["end"]))

    def check_overlap(name1, sch1, name2, sch2):
        error = 0
        eps = 0.01
        for tid1, s1, e1 in sch1:
            for tid2, s2, e2 in sch2:
                if tid1 == tid2:
                    continue
                if s1 + pd.Timedelta(seconds=eps) < e2  and s2 + pd.Timedelta(seconds=eps) < e1:
                    print(f"{name1} {tid1} 與 {name2} {tid2} 時間重疊")
                    print(f"    {tid1}: {s1} ~ {e1}")
                    print(f"    {tid2}: {s2} ~ {e2}")
                    error = 1
        return error

    e1 = check_overlap("Download", download_schedule, "Download", download_schedule)
    e2 = check_overlap("Remove", remove_schedule, "Download", download_schedule)
    e3 = check_overlap("Remove", remove_schedule, "Shoot", shoot_schedule)
    e4 = check_overlap("Remove", remove_schedule, "Remove", remove_schedule)
    e5 = check_overlap("Else", else_schedule, "Download", download_schedule)
    e6 = check_overlap("Else", else_schedule, "Remove", remove_schedule)
    e7 = check_overlap("Else", else_schedule, "Shoot", shoot_schedule)
    e8 = check_overlap("Else", else_schedule, "Else", else_schedule)

    return e1 or e2 or e3 or e4 or e5 or e6 or e7 or e8
