import msal
from env.context import Context

class Client:

    def __init__(self, context: Context):
        self.scope = None
        self._context = context

    def get_headers(self, graph=False, tenant=False):
        """
        Get the access token for the Power BI API
        """

        if self._context is None:
            raise RuntimeError("Context is None")

        sp = self._context.get_ServicePrincipal()
        tenant_id = sp.get("TenantId")
        client_id = sp.get("AppId")
        client_secret = sp.get("AppSecret")
        if not tenant_id or not client_id or not client_secret:
            raise RuntimeError("TENANT_ID, CLIENT_ID, and CLIENT_SECRET are required for token acquisition.")

        authority = f"{self._context.cloud.authority_host}/{tenant_id}"


        # Create a ConfidentialClientApplication object
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority
        )


        # This needs to stay as a list
        scopes = [self.scope]
        
        result = app.acquire_token_for_client(scopes=scopes)
        if "access_token" not in result:
            error = result.get("error", "authentication_failed")
            description = result.get("error_description", "Authentication failed.")
            message = f"Token acquisition failed for {self.scope}: {error}: {description}"
            if "AADSTS7000215" in description:
                message += (
                    " Use the client secret VALUE from the Entra app registration, "
                    "not the secret ID."
                )
            self._context.logger.error(message)
            raise RuntimeError(message)

        access_token = result["access_token"]
        return {'Authorization': f'Bearer {access_token}'}
