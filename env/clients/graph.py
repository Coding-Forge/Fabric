from .baseClient import Client

class GraphClient(Client):
    def __init__(self, context):
        super().__init__(context)
        self.scope = "https://graph.microsoft.com/.default"


    def get_api_root(self) -> str:
        return 'https://graph.microsoft.com/beta'