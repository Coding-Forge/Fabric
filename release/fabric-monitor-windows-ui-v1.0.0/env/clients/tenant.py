from .baseClient import Client

class TenantClient(Client):
    def __init__(self, context):
        super().__init__(context)
        if not context.cloud.supports_fabric_api:
            raise RuntimeError(
                f"Fabric REST APIs are not enabled for CLOUD_ENVIRONMENT={context.cloud.name}. "
                "Use Commercial until Fabric Gov is available."
            )
        self.scope = context.cloud.fabric_scope


    def get_api_root(self) -> str:
        return self._context.cloud.fabric_api_root
