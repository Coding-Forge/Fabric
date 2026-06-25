from .baseClient import Client

class PbiClient(Client):
    def __init__(self, context):
        super().__init__(context)
        self.scope = context.cloud.powerbi_scope


    def get_api_root(self) -> str:
        return self._context.cloud.powerbi_api_root
