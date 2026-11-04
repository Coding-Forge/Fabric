import threading
from typing import Optional

import msal

from env.context import Context


class Client:
    """Base client that acquires bearer tokens for a single resource scope.

    One MSAL ``ConfidentialClientApplication`` is created per client and reused,
    so tokens come from MSAL's in-memory cache until they near expiry.
    """

    def __init__(self, context: Context):
        self.scope = None
        self._context = context
        self._app: Optional[msal.ConfidentialClientApplication] = None
        self._app_key: Optional[tuple] = None
        self._lock = threading.Lock()

    def _get_app(self) -> msal.ConfidentialClientApplication:
        """Return the cached MSAL application, recreating it when credentials change.

        :return: The confidential client application for the configured service principal.
        :raises RuntimeError: If the context or service principal credentials are missing.
        """
        if self._context is None:
            raise RuntimeError("Context is None")

        sp = self._context.get_ServicePrincipal() or {}
        try:
            key = (
                sp["TenantId"], sp["AppId"], sp["AppSecret"],
                self._context.cloud.authority_host,
            )
        except KeyError as ex:
            raise RuntimeError(f"Service principal is missing {ex}") from ex

        with self._lock:
            if self._app is None or self._app_key != key:
                self._app = msal.ConfidentialClientApplication(
                    client_id=key[1],
                    client_credential=key[2],
                    authority=f"{key[3]}/{key[0]}",
                )
                self._app_key = key
            return self._app

    def get_headers(self, graph=False, tenant=False):
        """Return request headers carrying a bearer token for ``self.scope``.

        :param graph: Unused; kept for backwards compatibility.
        :param tenant: Unused; kept for backwards compatibility.
        :return: A dict with the ``Authorization`` header.
        :raises RuntimeError: If credentials are missing or token acquisition fails.
        """

        app = self._get_app()

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
                    message = result.get("error_description", "Authentication failed.")
                    if "AADSTS7000215" in message:
                        message += " Use the client secret VALUE, not the secret ID."
                    self._context.logger.error(f"Token acquisition failed for {self.scope}: {message}")
                    raise RuntimeError(f"Token acquisition failed for {self.scope}: {message}")

            return headers
        except RuntimeError:
            raise
        except Exception as ex:
            self._context.logger.error(f"An exception occurred while acquiring a token: {str(ex)}")
            raise
