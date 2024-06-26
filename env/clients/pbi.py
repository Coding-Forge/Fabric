from .baseClient import Client

class PbiClient(Client):
    def __init__(self, context):
        super().__init__(context)
        self.scope = "https://analysis.windows.net/powerbi/api/.default"


    def get_api_root(self) -> str:
        return 'https://api.powerbi.com/'