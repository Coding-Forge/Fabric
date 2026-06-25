from .baseClient import Client

class GraphClient(Client):
    def __init__(self, context):
        super().__init__(context)
        self.scope = context.cloud.graph_scope


    def get_api_root(self) -> str:
        return self._context.cloud.graph_api_root
