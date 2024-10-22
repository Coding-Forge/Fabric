from .context import Context


import asyncio
import platform
import asyncio
import json
import yaml
import sys
import os

from codetiming import Timer
from croniter import croniter
from env.modules import *

from env.clients import PbiClient, GraphClient, TenantClient
from datetime import datetime, timedelta
from env.utility.file_management import File_Management
from env.context import Context
import re

content = None


# from .monitor import main as Monitor
def is_function_due(cron_syntax, last_run):
    last_run_datetime = last_run

    cron = croniter(cron_syntax, last_run_datetime)
    next_run_datetime = cron.get_next(datetime)
    
    # print(f"What is the next run date value {next_run_datetime} and what is the current datetime {datetime.now()}")

    if next_run_datetime.strftime("%Y-%m-%d %H:%M") <= datetime.now().strftime("%Y-%m-%d %H:%M"):
        return True
    else:
        return False


class Audits:
    def __init__(self):
        self.context = Context()
        self.fm = File_Management()
    
    def __setup_clients(self):
        self.context.clients["pbi"] = PbiClient(self.context)
        self.context.clients["graph"] = GraphClient(self.context)
        self.context.clients["tenant"] = TenantClient(self.context)

    def set_logging_config(self, log_level, log_file):
        self.context.set_log_config(log_level, log_file)

    async def run(self):

        self.__setup_clients()
        
        # print(f"service principal: {self.context._ServicePrincipal}")
        # settings = bob.get_settings()
        # get the state.yaml file that include information about the last run

        # replacing get_st8te
        self.fm.content(self.context)
        self.context.set_FileManagement(self.fm)

        try:
            current_state = await self.fm.read(file_name="state.yaml")
            print(f"what is the current state {current_state}")
            
            if not current_state:
                current_state = await self.create_state()

            self.context.set_current_state(current_state)

        except Exception as e:
            self.context.logger.error("Error retrieve state.yaml file")
            print(f"Error: {e}")

        # get the modules selected in the configuration for the application
        # modules = settings.get("ApplicationModules").replace(" ","").split(",")
        modules = self.context.ApplicationModules.replace(" ","").split(",")
        
        run_jobs = []

        work_queue = asyncio.Queue()

        for module in modules:
            cron = self.context.get_cron(module)
            

            run_jobs.append(module)
            try:
                if isinstance(current_state, str):
                    current_state = json.loads(current_state)
                # else:

                run = current_state.get(f"{module.lower()}",{}).get("lastRun")

                if not run:
                    run_jobs.append(module)
                    current_state[module.lower()] =  {"lastRun": "2024-05-31T04:00:31.000683Z"}
                else:
                    last_run = self.context.convert_dt_str(run)   

                    if is_function_due(cron,last_run):
                        run_jobs.append(module)
            except:
                # most likely the this is the first time running the module and will build the state.yaml file at the end
                run_jobs.append(module)
                if isinstance(current_state, str):
                    current_state = json.loads(current_state)
                    
                current_state[module.lower()] =  {"lastRun": "2024-05-31T04:00:31.000683Z"}
                pass

        if len(run_jobs) == 0:
            print("No jobs to run")
            return


        try:
            classes = [globals()[module] for module in run_jobs]

            for module in classes:
                await work_queue.put(module)
        except Exception as e:
            self.context.logger.error(f"Error check globals: {e}")

            print(f"Error check globals: {e}")
            return

        def remove_carriage_returns(string):
            return re.sub(r'\r', '', string.strip())

        async def task(name, work_queue, content):
            timer = Timer(text=f"Task {name} elapsed time: {{:.1f}}")
            while not work_queue.empty():
                module = await work_queue.get()
                self.context.logger.info(f"Task {remove_carriage_returns(module.__doc__)} is now running")
                print(f"Task {remove_carriage_returns(module.__doc__)} is now running")
                timer.start()
                await module(content)
                timer.stop()

        gather_tasks = []
        for module in run_jobs:
            gather_tasks.append(asyncio.create_task(task(f"{module}", work_queue, content=self.context)))

        with Timer(text="\nTotal elapsed time: {:.1f}"):
            await asyncio.gather(*gather_tasks)

        if isinstance(current_state, str):
            current_state = json.loads(current_state)

        for job in run_jobs:
            current_state[job.lower()]["lastRun"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        try:
            self.fm.content(self.context)
            await self.fm.save("", "state.yaml", current_state)
        except Exception as e:
            self.context.logger.error(f"Error saving state.yaml file: {e}")
            print(f"fm Error: {e}")


    async def create_state(self):
        print("Creating state.yaml file")
        self.fm.content(self.context)

        now = datetime.now()
        yesterday = now - timedelta(days=7)
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
            }, "domains": {
                "lastRun": state_now
            }, "fabricitems": {
                "lastRun": state_now
            }, "workspaces": {
                "lastRun": state_now
            }
        }

        await self.fm.save("", "state.yaml", current_state)
        return current_state
    
    def set_all_workspaces(self, get_all_workspaces:bool):
        return self.context.set_all_workspaces(get_all_workspaces)

    def set_WorkspaceName(self, WorkspaceName):
        self.context.set_WorkspaceName(WorkspaceName)

    def set_StorageAccountConnStr(self, StorageAccountConnStr):
        self.context.set_StorageAccountConnStr(StorageAccountConnStr)
    
    def set_storage_url(self, storage_url):
        self.context.set_storage_url(storage_url)

    def set_Domains_cron(self, Domains_cron):    
        self.context.set_Domains_cron(Domains_cron)

    def set_StorageAccountContainerName(self, StorageAccountContainerName):
        self.context.set_StorageAccountContainerName(StorageAccountContainerName)

    def set_StorageAccountContainerRootPath(self, StorageAccountContainerRootPath): 
        self.context.set_StorageAccountContainerRootPath(StorageAccountContainerRootPath)

    def set_OutputPath(self, OutputPath):
        self.context.set_OutputPath(OutputPath)

    def set_CatlogGetModifiedParameters(self, CatalogGetModifiedParameters):
        self.context.set_CatlogGetModifiedParameters(CatalogGetModifiedParameters)

    def set_CatoalogGetInfoParameters(self, CatalogGetInfoParameters):
        self.context.set_CatoalogGetInfoParameters(CatalogGetInfoParameters)

    def set_ServicePrincipal(self, tenant_id, client_id, client_secret):
        self.context.set_ServicePrincipal(TenantId=tenant_id, AppId=client_id, AppSecret=client_secret, Environment="Public")

    def set_LakehouseName(self, LakehouseName):
        self.context.set_LakehouseName(LakehouseName)
    
    def set_PathInLakehouse(self, PathInLakehouse):
        self.context.set_PathInLakehouse(PathInLakehouse)

    def set_Activity_cron(self, Activity_cron):
        self.context.set_Activity_cron(Activity_cron)
    
    def set_Apps_cron(self, Apps_cron):
        self.context.set_Apps_cron(Apps_cron)

    def set_Catalog_cron(self, Catalog_cron):
        self.context.set_Catalog_cron(Catalog_cron)

    def set_Graph_cron(self, Graph_cron):
        self.context.set_Graph_cron(Graph_cron)

    def set_Tenant_cron(self, Tenant_cron):
        self.context.set_Tenant_cron(Tenant_cron)

    def set_RefreshHistory_cron(self, RefreshHistory_cron):
        self.context.set_RefreshHistory_cron(RefreshHistory_cron)
    
    def set_Refreshables_cron(self, Refreshables_cron):
        self.context.set_Refreshables_cron(Refreshables_cron)

    def set_Gateway_cron(self, Gateway_cron):
        self.context.set_Gateway_cron(Gateway_cron)

    def set_Capacity_cron(self, Capacity_cron):
        self.context.set_Capacity_cron(Capacity_cron)

    def set_Roles_cron(self, Roles_cron):
        self.context.set_Roles_cron(Roles_cron)

    def set_ApplicationModules(self, ApplicationModules):
        self.context.set_ApplicationModules(ApplicationModules)

    def exclude_personal_workspaces(self, exclude_personal_workspaces):
        self.context.exclude_personal_workspaces(exclude_personal_workspaces)

    def exclude_inactivate_workspaces(self, exclude_personal_workspaces):
        self.context.exclude_inactivate_workspaces(exclude_personal_workspaces)