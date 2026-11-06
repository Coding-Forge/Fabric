"""E9: baseClient reuses one MSAL app (token cache) and fails clearly on missing credentials."""
import unittest
from unittest.mock import MagicMock, patch

from env.clients import baseClient
from env.clients.baseClient import Client
from env.cloud import get_cloud_profile
from tests.helpers import make_context

SP = {"TenantId": "tenant-1", "AppId": "app-1", "AppSecret": "secret-1", "Environment": "Public"}


def _client(sp=SP, scope="https://scope/.default"):
    ctx = make_context()
    ctx.ServicePrincipal = dict(sp) if sp is not None else sp
    c = Client(ctx)
    c.scope = scope
    return c, ctx


class BaseClientTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(baseClient.msal, "ConfidentialClientApplication")
        self.app_cls = p.start()
        self.addCleanup(p.stop)
        self.app = self.app_cls.return_value
        self.app.acquire_token_for_client.return_value = {"access_token": "tok"}

    def test_app_created_with_service_principal(self):
        c, _ = _client()
        c.get_headers()
        self.app_cls.assert_called_once_with(
            client_id="app-1", client_credential="secret-1",
            authority="https://login.microsoftonline.com/tenant-1")

    def test_headers_carry_bearer_token_for_scope(self):
        c, _ = _client()
        self.assertEqual(c.get_headers(), {"Authorization": "Bearer tok"})
        self.app.acquire_token_for_client.assert_called_once_with(scopes=["https://scope/.default"])

    def test_app_is_cached_across_calls(self):
        c, _ = _client()
        for _ in range(5):
            c.get_headers()
        self.assertEqual(self.app_cls.call_count, 1)
        self.assertEqual(self.app.acquire_token_for_client.call_count, 5)

    def test_forced_renewal_evicts_tokens_without_recreating_the_application(self):
        c, _ = _client()
        c.get_headers()
        self.app.remove_tokens_for_client.assert_not_called()
        c.get_headers(force_refresh=True)
        self.app.remove_tokens_for_client.assert_called_once_with()
        self.assertEqual(self.app_cls.call_count, 1)
        self.assertEqual(self.app.acquire_token_for_client.call_count, 2)

    def test_get_app_returns_same_instance(self):
        c, _ = _client()
        self.assertIs(c._get_app(), c._get_app())

    def test_app_recreated_when_credentials_change(self):
        c, ctx = _client()
        c.get_headers()
        ctx.ServicePrincipal = {**SP, "AppSecret": "rotated"}
        c.get_headers()
        self.assertEqual(self.app_cls.call_count, 2)
        self.assertEqual(self.app_cls.call_args.kwargs["client_credential"], "rotated")

    def test_cloud_authority_change_invalidates_cached_app(self):
        c, ctx = _client()
        c.get_headers()
        ctx.cloud = get_cloud_profile("GccHigh")
        c.get_headers()
        c.get_headers()
        self.assertEqual(self.app_cls.call_count, 2)
        self.assertEqual(
            self.app_cls.call_args.kwargs["authority"],
            "https://login.microsoftonline.us/tenant-1",
        )

    def test_each_client_has_its_own_app(self):
        a, _ = _client()
        b, _ = _client()
        a.get_headers()
        b.get_headers()
        self.assertEqual(self.app_cls.call_count, 2)

    def test_none_context_raises_runtime_error(self):
        c = Client(None)
        with self.assertRaises(RuntimeError):
            c.get_headers()
        self.app_cls.assert_not_called()

    def test_missing_credentials_raise_runtime_error(self):
        for sp in (None, {}, {"TenantId": "t", "AppId": "a"}, {"TenantId": "t", "AppSecret": "s"},
                   {"AppId": "a", "AppSecret": "s"}):
            with self.subTest(sp=sp):
                c, _ = _client(sp)
                with self.assertRaises(RuntimeError):
                    c.get_headers()
        self.app_cls.assert_not_called()

    def test_token_failure_raises_runtime_error_with_description(self):
        self.app.acquire_token_for_client.return_value = {"error_description": "bad secret"}
        c, ctx = _client()
        with self.assertRaises(RuntimeError) as cm:
            c.get_headers()
        self.assertIn("bad secret", str(cm.exception))
        ctx.logger.error.assert_called()

    def test_token_failure_without_description_uses_generic_message(self):
        self.app.acquire_token_for_client.return_value = {}
        c, _ = _client()
        with self.assertRaisesRegex(RuntimeError, "Authentication failed"):
            c.get_headers()

    def test_unexpected_msal_exception_is_logged_and_reraised(self):
        self.app.acquire_token_for_client.side_effect = ValueError("network")
        c, ctx = _client()
        with self.assertRaises(ValueError):
            c.get_headers()
        ctx.logger.error.assert_called()

    def test_failed_acquisition_does_not_discard_cached_app(self):
        self.app.acquire_token_for_client.side_effect = [{"error_description": "x"}, {"error_description": "x"},
                                                         {"access_token": "ok"}]
        c, _ = _client()
        with self.assertRaises(RuntimeError):
            c.get_headers()
        self.assertEqual(c.get_headers(), {"Authorization": "Bearer ok"})
        self.assertEqual(self.app_cls.call_count, 1)


if __name__ == "__main__":
    unittest.main()
