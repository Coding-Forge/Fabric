from .baseClient import Client

class TenantClient(Client):
    def __init__(self, context):
        super().__init__(context)
        self.scope = "https://api.fabric.microsoft.com/.default"


    def get_api_root(self) -> str:
        return 'https://api.fabric.microsoft.com/'