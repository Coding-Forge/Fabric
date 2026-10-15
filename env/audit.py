import asyncio
import re
from datetime import datetime, timedelta

import yaml
from codetiming import Timer
from croniter import croniter

from env.clients import GraphClient, PbiClient, TenantClient
from env.context import Context, utc_now, utc_stamp
from env.modules import *
from env.utility.file_management import File_Management

from .context import Context

content = None


# from .monitor import main as Monitor
def is_function_due(cron_syntax, last_run):
    # If no cron is configured, always run the module
    if not cron_syntax:
        return True

    # Cron expressions are evaluated in UTC: ``last_run`` is a naive UTC datetime
    # and the result is compared with ``utc_now()``. The Azure Functions timer
    # trigger in function_app.py also runs in UTC unless WEBSITE_TIME_ZONE is set,
    # which affects only that trigger schedule, not these module cron settings.
    last_run_datetime = last_run

    cron = croniter(cron_syntax, last_run_datetime)
    next_run_datetime = cron.get_next(datetime)

    # print(f"What is the next run date value {next_run_datetime} and what is the current datetime {datetime.now()}")

    # State timestamps are UTC, so compare against UTC
    if next_run_datetime.strftime("%Y-%m-%d %H:%M") <= utc_now().strftime(
        "%Y-%m-%d %H:%M"
    ):
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

        # A read failure must abort the run: defaulting to {} would overwrite the real
        # state file with fresh checkpoints. Only a missing/empty state starts fresh.
        try:
            current_state = await self.fm.read(file_name="state.yaml")
            print(f"what is the current state {current_state}")

            if isinstance(current_state, str):
                # Local/Lakehouse reads return text (blob returns parsed YAML).
                # JSON is valid YAML, so safe_load handles both formats.
                # Blank content (e.g. a zero-byte file) means no state yet.
                current_state = (
                    yaml.safe_load(current_state) if current_state.strip() else None
                )

            if current_state is not None and not isinstance(current_state, dict):
                raise ValueError("state.yaml does not contain a mapping")

            if not current_state:
                current_state = await self.create_state()

        except Exception as e:
            self.context.logger.error(
                f"Error retrieving state.yaml; aborting run without saving state: {e}"
            )
            print(f"Error: {e}")
            return

        # The context shares this same dict, so modules can persist extra keys
        # (for example catalog.lastFullScan) that are saved with the final state.
        self.context.set_current_state(current_state)

        # get the modules selected in the configuration for the application
        # modules = settings.get("ApplicationModules").replace(" ","").split(",")
        modules = self.context.ApplicationModules.replace(" ", "").split(",")

        run_jobs = []

        work_queue = asyncio.Queue()

        for module in modules:
            cron = self.context.get_cron(module)
            key = module.lower()

            module_entry = current_state.get(key)
            run = (
                module_entry.get("lastRun") if isinstance(module_entry, dict) else None
            )

            if not run:
                # First time the module runs: seed a bounded look-back window
                run_jobs.append(module)
                self._module_state(current_state, key)["lastRun"] = (
                    self._default_last_run()
                )
                continue

            try:
                last_run = self.context.convert_dt_str(run)
            except ValueError:
                # Unparseable checkpoint: rerun with a bounded look-back window
                run_jobs.append(module)
                self._module_state(current_state, key)["lastRun"] = (
                    self._default_last_run()
                )
                continue

            if is_function_due(cron, last_run):
                run_jobs.append(module)

        if len(run_jobs) == 0:
            print("No jobs to run")
            return

        print(f"Running jobs: {run_jobs}")

        try:
            classes = {module: globals()[module] for module in run_jobs}

            for name, module in classes.items():
                await work_queue.put((name, module))
        except Exception as e:
            self.context.logger.error(f"Error check globals: {e}")

            print(f"Error check globals: {e}")
            return

        def remove_carriage_returns(string):
            return re.sub(r"\r", "", string.strip())

        # module name -> True when the module completed successfully
        outcomes: dict = {}

        async def task(name, work_queue, content):
            timer = Timer(text=f"Task {name} elapsed time: {{:.1f}}")
            while not work_queue.empty():
                module_name, module = await work_queue.get()
                self.context.logger.info(
                    f"Task {remove_carriage_returns(module.__doc__)} is now running"
                )
                print(f"Task {remove_carriage_returns(module.__doc__)} is now running")
                timer.start()
                try:
                    # A module signals failure by returning False or raising
                    outcomes[module_name] = (await module(content)) is not False
                except Exception as e:
                    outcomes[module_name] = False
                    self.context.logger.error(f"Module {module_name} failed: {e}")
                    print(f"Module {module_name} failed: {e}")
                finally:
                    timer.stop()

        gather_tasks = []
        for module in run_jobs:
            gather_tasks.append(
                asyncio.create_task(task(f"{module}", work_queue, content=self.context))
            )

        with Timer(text="\nTotal elapsed time: {:.1f}"):
            results = await asyncio.gather(*gather_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                self.context.logger.error(f"Task failed unexpectedly: {result}")
                print(f"Task failed unexpectedly: {result}")

        # Only advance lastRun for modules that succeeded so failed days are retried
        now_str = utc_stamp()
        for job in run_jobs:
            if outcomes.get(job):
                self._module_state(current_state, job.lower())["lastRun"] = now_str
            else:
                self.context.logger.warning(
                    f"Module {job} did not complete; lastRun not advanced"
                )
                print(f"Module {job} did not complete; lastRun not advanced")

        try:
            self.fm.content(self.context)
            await self.fm.save("", "state.yaml", current_state)
        except Exception as e:
            self.context.logger.error(f"Error saving state.yaml file: {e}")
            print(f"fm Error: {e}")

    @staticmethod
    def _default_last_run() -> str:
        """Return the default first-run checkpoint (seven days ago) as a state timestamp."""
        return utc_stamp(utc_now() - timedelta(days=7))

    @staticmethod
    def _module_state(state: dict, key: str) -> dict:
        """Return the mutable state entry for a module, repairing a null or non-dict entry.

        :param state: The full state mapping.
        :param key: Lower-case module key.
        :return: The module's state dict, stored in ``state``.
        """
        entry = state.get(key)
        if not isinstance(entry, dict):
            entry = {}
            state[key] = entry
        return entry

    async def create_state(self):
        print("Creating state.yaml file")
        self.fm.content(self.context)

        state_now = self._default_last_run()
        current_state = {
            "activity": {"lastRun": state_now},
            "apps": {"lastRun": state_now},
            "catalog": {"lastRun": state_now},
            "gateway": {"lastRun": state_now},
            "graph": {"lastRun": state_now},
            "refreshables": {"lastRun": state_now},
            "refreshhistory": {"lastRun": state_now},
            "tenant": {"lastRun": state_now},
            "capacity": {"lastRun": state_now},
            "roles": {"lastRun": state_now},
            "domains": {"lastRun": state_now},
            "fabricitems": {"lastRun": state_now},
            "workspaces": {"lastRun": state_now},
            "gitconnections": {"lastRun": state_now},
            "tags": {"lastRun": state_now},
            "delegatedsettings": {"lastRun": state_now},
            "widelysharedlinks": {"lastRun": state_now},
        }

        await self.fm.save("", "state.yaml", current_state)
        return current_state

    def set_on_fabric(self, on_fabric: bool):
        self.context.set_on_fabric(on_fabric)

    def set_all_workspaces(self, get_all_workspaces: bool):
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
        self.context.set_StorageAccountContainerRootPath(
            StorageAccountContainerRootPath
        )

    def set_OutputPath(self, OutputPath):
        self.context.set_OutputPath(OutputPath)

    def set_CatlogGetModifiedParameters(self, CatalogGetModifiedParameters):
        self.context.set_CatlogGetModifiedParameters(CatalogGetModifiedParameters)

    def set_capacity_metrics_dataset_id(self, capacity_metrics_dataset_id):
        self.context.set_capacity_metrics_dataset_id(capacity_metrics_dataset_id)

    def set_CatalogGetInfoParameters(self, CatalogGetInfoParameters):
        self.context.set_CatalogGetInfoParameters(CatalogGetInfoParameters)

    def set_ServicePrincipal(self, tenant_id, client_id, client_secret):
        self.context.set_ServicePrincipal(
            TenantId=tenant_id,
            AppId=client_id,
            AppSecret=client_secret,
            Environment="Public",
        )

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

    def set_FabricItems_cron(self, FabricItems_cron):
        self.context.set_FabricItems_cron(FabricItems_cron)

    def set_Workspaces_cron(self, Workspaces_cron):
        self.context.set_Workspaces_cron(Workspaces_cron)

    def set_CapacityMetrics_cron(self, CapacityMetrics_cron):
        self.context.set_CapacityMetrics_cron(CapacityMetrics_cron)

    def set_GitConnections_cron(self, GitConnections_cron):
        self.context.set_GitConnections_cron(GitConnections_cron)

    def set_Tags_cron(self, Tags_cron):
        self.context.set_Tags_cron(Tags_cron)

    def set_DelegatedSettings_cron(self, DelegatedSettings_cron):
        self.context.set_DelegatedSettings_cron(DelegatedSettings_cron)

    def set_WidelySharedLinks_cron(self, WidelySharedLinks_cron):
        self.context.set_WidelySharedLinks_cron(WidelySharedLinks_cron)

    def set_ApplicationModules(self, ApplicationModules):
        self.context.set_ApplicationModules(ApplicationModules)

    def exclude_personal_workspaces(self, exclude_personal_workspaces):
        self.context.set_exclude_personal_workspaces(exclude_personal_workspaces)

    def exclude_inactivate_workspaces(self, exclude_personal_workspaces):
        self.context.set_exclude_inactive_workspaces(exclude_personal_workspaces)

    def set_ImpersonatedUserName(self, impersonatedUserName):
        self.context.set_ImpersonatedUserName(impersonatedUserName)
