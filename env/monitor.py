import platform
import asyncio
import json
import yaml
import sys
import logging
import os

from codetiming import Timer
from croniter import croniter

from env.modules.activity import main as Activity
from env.modules.apps import main as Apps
from env.modules.catalog import main as Catalog
from env.modules.graph import main as Graph
from env.modules.tenant import main as Tenant
from env.modules.refreshhistory import main as RefreshHistory
from env.modules.refreshables import main as Refreshables
from env.modules.gateway import main as Gateway
from env.modules.capacity import main as Capacity
from env.modules.roles import main as Roles
from datetime import datetime, timedelta
from env.utility.helps import Bob
from env.utility.file_management import File_Management


async def tasker(name, work_queue):
    while not work_queue.empty():
        module = await work_queue.get()
        print(f"Task {name} running {module.__name__}")
        await module()
        work_queue.task_done()

async def task(name, work_queue):
    timer = Timer(text=f"Task {name} elapsed time: {{:.1f}}")
    while not work_queue.empty():
        module = await work_queue.get()
        
        print(f"Task {name} running {module.__name__}")
        timer.start()
        await module()
        timer.stop()


def is_function_due(cron_syntax, last_run):
    last_run_datetime = last_run

    cron = croniter(cron_syntax, last_run_datetime)
    next_run_datetime = cron.get_next(datetime)
    
    print(f"What is the next run date value {next_run_datetime} and what is the current datetime {datetime.now()}")

    if next_run_datetime.strftime("%Y-%m-%d %H:%M") <= datetime.now().strftime("%Y-%m-%d %H:%M"):
        return True
    else:
        return False



async def Monitor():
    # Your code here
    bob = Bob()
    fm = File_Management()
    settings = bob.get_settings()
    # get the state.yaml file that include information about the last run

    # replacing get_st8te
    fm = File_Management()
    try:
        current_state = await fm.read(file_name="state.yaml")
        if not current_state:
            now = datetime.now()
            yesterday = now - timedelta(days=1)
            state_now = yesterday.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            current_state = {
                "activity": {
                    "lastRun": state_now
                }, "apps": {
                    "lastRun": state_now
                }, "catalog": {
                    "lastFullScan": state_now,
                    "lastRun": state_now
                }, "gateway": {
                    "lastRun": state_now
                }, "graph": {
                    "lastRun": state_now
                }, "refreshables": {
                    "lastRun": state_now
                }, "refreshhistory": {
                    "lastRun": state_now
                }, "tenant": {
                    "lastRun": state_now
                }, "capacity": {
                    "lastRun": state_now
                }, "roles": {
                    "lastRun": state_now
                }
            }

            await fm.save("stage", "state.yaml", current_state)
    except Exception as e:
        print(f"Error: {e}")
        return


    print(f"what is the state {current_state}")

    # get the modules selected in the configuration for the application
    modules = settings.get("ApplicationModules").replace(" ","").split(",")
    # print(f"what are the modules {modules}")
    run_jobs = []


    work_queue = asyncio.Queue()

    for module in modules:
        cron = settings.get(f"{module}_cron")
        try:
            if isinstance(current_state, str):
                run = json.loads(current_state).get(f"{module.lower()}").get("lastRun")
            else:
                run = current_state.get(f"{module.lower()}").get("lastRun")

            last_run = bob.convert_dt_str(run)    
            if is_function_due(cron,last_run):
                logging.info(f"The following module added to the run queue {module}")
                run_jobs.append(module)
        except:
            # most likely the this is the first time running the module and will build the state.yaml file at the end
            run_jobs.append(module)
            current_state[module.lower()] =  {"lastRun": "2024-05-31T04:00:31.000683Z"}
            pass

    if len(run_jobs) == 0:
        print("No jobs to run")
        return

    classes = [globals()[module] for module in run_jobs]

    for module in classes:
        await work_queue.put(module)
    

    # tasks = await create_module_tasks(dynamic_modules)

    # Run tasks concurrently using asyncio.gather()
    # results = await asyncio.gather(*tasks)


    with Timer(text="\nTotal elapsed time: {:.1f}"):
        await asyncio.gather(
            asyncio.create_task(task("Activity", work_queue)),
            asyncio.create_task(task("Apps", work_queue)),
            asyncio.create_task(task("Catalog", work_queue)),
            asyncio.create_task(task("Graph", work_queue)),
            asyncio.create_task(task("Tenant", work_queue)),
            asyncio.create_task(task("Gateway", work_queue)),
            asyncio.create_task(task("Refresh History", work_queue))
        )


    # this has all the information needed to modify the state.yaml file
    # update the state.yaml file with the last run information

    if isinstance(current_state, str):
        current_state = json.loads(current_state)

    for job in run_jobs:
        current_state[job.lower()]["lastRun"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    try:
        await fm.save("", "state.yaml", current_state)
    except Exception as e:
        print(f"fm Error: {e}")


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(Monitor())
