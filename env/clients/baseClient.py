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

        try:
            if self._context is None:
                print("Context is None")

            sp = self._context.get_ServicePrincipal()
            tenant_id = sp['TenantId']
            client_id = sp['AppId']
            client_secret = sp['AppSecret']

        except Exception as e:
            self._context.logger.error(f"An exception occurred while reading the file: {str(e)}")

            print("An exception occurred while reading the file:", str(e))

        authority = f"https://login.microsoftonline.com/{tenant_id}"


        # Create a ConfidentialClientApplication object
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority
        )


        # This needs to stay as a list
        scopes = [self.scope]
        
        # Acquire a token using client credentials
        try:
            result = app.acquire_token_for_client(scopes=scopes)
            if "access_token" in result:
                access_token = result["access_token"]
                # Use the access token to make API calls to Power BI
                headers = {'Authorization': f'Bearer {access_token}'}

            else:
                # If silent token acquisition fails, fallback to interactive authentication
                result = app.acquire_token_for_client(scopes=scopes)

                if "access_token" in result:
                    # TODO: Add your Power BI API calls here
                    access_token = result["access_token"]
                    # Use the access token to make API calls to Power BI
                    headers = {'Authorization': f'Bearer {access_token}'}

                else:
                    print(result.get("error_description", "Authentication failed."))

            return headers
            
        except Exception as ex:
            self._context.logger.error(f"An exception occurred while reading the file: {str(ex)}")
            print(ex)