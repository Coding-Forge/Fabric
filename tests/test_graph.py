"""Graph module: uses context.invokeAPI, honours GraphExtractGroups and reports failures."""

import os
import unittest
from unittest.mock import MagicMock, patch

import aiohttp

from env.context import Context
from env.modules import graph
from tests.helpers import make_context

ROOT = "https://graph.test/v1.0"


def _ctx(routes, groups=False):
    """``routes`` maps a URL prefix to the invokeAPI response."""
    calls = []

    async def invoke(rest_api, headers=None, json=None):
        calls.append((rest_api, headers))
        for prefix, resp in routes.items():
            if rest_api.startswith(prefix):
                if isinstance(resp, BaseException):
                    raise resp
                return resp
        raise AssertionError(rest_api)

    ctx = make_context(invoke=invoke)
    ctx.GraphExtractGroups = groups
    client = MagicMock()
    client.get_headers.return_value = {"Authorization": "g"}
    client.get_api_root.return_value = ROOT
    ctx.clients["graph"] = client
    return ctx, calls


def _saved(ctx):
    return {
        c.kwargs["file_name"]: c.kwargs["content"] for c in ctx.fm.save.await_args_list
    }


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_audience_ids_override_name_prefixes(self):
        ctx, calls = _ctx(_group_routes(
            [{"id": "g1", "displayName": "PowerBI old"}, {"id": "g2", "displayName": "Nested"}],
            {"g1": {"value": []}, "g2": {"value": [{"id": "nested-user"}]}},
        ), groups=True)
        ctx.PowerBIAudienceGroupIds = " G2 "
        self.assertTrue(await graph.main(ctx))
        saved = _saved(ctx)
        self.assertEqual(
            [group["isPowerBIAudienceGroup"] for group in saved["groups.json"]],
            [False, True],
        )
        self.assertEqual(saved["groupmembers.json"][0]["memberId"], "nested-user")
        self.assertTrue(any("/transitiveMembers/microsoft.graph.user" in url for url, _ in calls))

    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await graph.main(None)

    async def test_calls_go_through_invoke_api_with_graph_root_and_headers(self):
        ctx, calls = _ctx(
            {
                f"{ROOT}/users": {"value": [{"id": "u"}]},
                f"{ROOT}/subscribedSkus": {"value": [{"id": "s"}]},
            }
        )
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual(
            [c[0].split("?")[0] for c in calls],
            [f"{ROOT}/users", f"{ROOT}/subscribedSkus"],
        )
        for _, headers in calls:
            self.assertEqual(headers["Authorization"], "g")
            self.assertEqual(headers["Content-Type"], "application/json")
        saved = _saved(ctx)
        self.assertEqual(saved["users.json"], [{"id": "u"}])
        self.assertEqual(saved["subscribedskus.json"], [{"id": "s"}])
        self.assertNotIn("groups.json", saved)
        for c in ctx.fm.save.await_args_list:
            self.assertTrue(c.kwargs["path"].startswith("graph/"))

    async def test_groups_are_fetched_when_enabled(self):
        ctx, calls = _ctx(
            {
                f"{ROOT}/users": {"value": [1]},
                f"{ROOT}/subscribedSkus": {"value": [2]},
                f"{ROOT}/groups": {"value": [3]},
            },
            groups=True,
        )
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual(len(calls), 3)
        self.assertEqual(_saved(ctx)["groups.json"], [3])

    async def test_failed_call_returns_false_but_other_calls_still_saved(self):
        ctx, calls = _ctx(
            {f"{ROOT}/users": {"ERROR": "x"}, f"{ROOT}/subscribedSkus": {"value": [2]}}
        )
        self.assertIs(await graph.main(ctx), False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(_saved(ctx)), ["subscribedskus.json"])
        ctx.logger.error.assert_called()

    async def test_invoke_api_exception_on_users_returns_false_without_crash(self):
        for exc in (aiohttp.ClientError("conn reset"), TimeoutError()):
            with self.subTest(exc=type(exc).__name__):
                ctx, calls = _ctx(
                    {
                        f"{ROOT}/users": exc,
                        f"{ROOT}/subscribedSkus": {"value": [2]},
                    }
                )
                self.assertIs(await graph.main(ctx), False)
                self.assertEqual(len(calls), 2)
                saved = _saved(ctx)
                self.assertEqual(list(saved), ["subscribedskus.json"])
                self.assertNotIn("userlicenses.json", saved)
                ctx.logger.error.assert_called()

    async def test_empty_response_is_a_failure(self):
        ctx, _ = _ctx({f"{ROOT}/users": None, f"{ROOT}/subscribedSkus": {}})
        self.assertIs(await graph.main(ctx), False)
        ctx.fm.save.assert_not_awaited()


def _env(**kw):
    return patch.dict(os.environ, kw)


def _clear_env():
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GRAPH_AUDIENCE_GROUP_PREFIXES", "GRAPH_MAX_GROUPS_FOR_MEMBERS")
    }
    return patch.dict(os.environ, env, clear=True)


def _group_routes(groups, members, users=None):
    """members: {groupId: response}. Groups route must precede the generic ones."""
    routes = {
        f"{ROOT}/users": {"value": users or []},
        f"{ROOT}/subscribedSkus": {"value": []},
        f"{ROOT}/groups?": {"value": groups},
    }
    for gid, resp in members.items():
        routes[f"{ROOT}/groups/{gid}/transitiveMembers"] = resp
    return routes


class GraphPagingAndLicenseTests(unittest.IsolatedAsyncioTestCase):
    async def test_users_next_link_pages_are_combined(self):
        next_url = f"{ROOT}/users?$skiptoken=abc"
        pages = [
            {"value": [{"id": "u1"}], "@odata.nextLink": next_url},
            {"value": [{"id": "u2"}]},
        ]
        calls = []

        async def invoke(rest_api, headers=None, json=None):
            calls.append(rest_api)
            if rest_api.startswith(f"{ROOT}/subscribedSkus"):
                return {"value": []}
            return pages.pop(0)

        ctx = make_context(invoke=invoke)
        ctx.GraphExtractGroups = False
        client = MagicMock()
        client.get_headers.return_value = {}
        client.get_api_root.return_value = ROOT
        ctx.clients["graph"] = client
        self.assertIs(await graph.main(ctx), True)
        self.assertIn(next_url, calls)
        self.assertEqual(_saved(ctx)["users.json"], [{"id": "u1"}, {"id": "u2"}])

    async def test_second_page_failure_fails_the_call(self):
        pages = [
            {"value": [{"id": "u1"}], "@odata.nextLink": f"{ROOT}/next"},
            {"ERROR": "boom"},
        ]

        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith(f"{ROOT}/subscribedSkus"):
                return {"value": []}
            return pages.pop(0)

        ctx = make_context(invoke=invoke)
        ctx.GraphExtractGroups = False
        client = MagicMock()
        client.get_headers.return_value = {}
        client.get_api_root.return_value = ROOT
        ctx.clients["graph"] = client
        self.assertIs(await graph.main(ctx), False)
        saved = _saved(ctx)
        self.assertNotIn("users.json", saved)
        self.assertNotIn("userlicenses.json", saved)

    async def test_userlicenses_one_row_per_user_per_license(self):
        users = [
            {
                "id": "u1",
                "userPrincipalName": "a@x",
                "assignedLicenses": [
                    {"skuId": "s1", "disabledPlans": ["p1", "p2"]},
                    {"skuId": "s2", "disabledPlans": []},
                ],
            },
            {"id": "u2", "userPrincipalName": "b@x", "assignedLicenses": []},
            {"id": "u3", "userPrincipalName": "c@x"},
            {
                "id": "u4",
                "userPrincipalName": "d@x",
                "assignedLicenses": [{"skuId": "s1"}],
            },
        ]
        ctx, _ = _ctx(
            {f"{ROOT}/users": {"value": users}, f"{ROOT}/subscribedSkus": {"value": []}}
        )
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual(
            _saved(ctx)["userlicenses.json"],
            [
                {
                    "userId": "u1",
                    "userPrincipalName": "a@x",
                    "skuId": "s1",
                    "disabledPlans": ["p1", "p2"],
                },
                {
                    "userId": "u1",
                    "userPrincipalName": "a@x",
                    "skuId": "s2",
                    "disabledPlans": [],
                },
                {
                    "userId": "u4",
                    "userPrincipalName": "d@x",
                    "skuId": "s1",
                    "disabledPlans": [],
                },
            ],
        )

    async def test_no_licensed_users_saves_empty_userlicenses(self):
        ctx, _ = _ctx(
            {
                f"{ROOT}/users": {"value": [{"id": "u"}]},
                f"{ROOT}/subscribedSkus": {"value": []},
            }
        )
        await graph.main(ctx)
        self.assertEqual(_saved(ctx)["userlicenses.json"], [])


class GraphGroupTests(unittest.IsolatedAsyncioTestCase):
    async def test_audience_flag_default_prefixes(self):
        groups = [
            {"id": "1", "displayName": "PowerBI Sales"},
            {"id": "2", "displayName": "power bi Finance"},
            {"id": "3", "displayName": "Finance"},
            {"id": "4", "displayName": "My PowerBI"},
            {"id": "5"},
        ]
        ctx, _ = _ctx(
            _group_routes(groups, {g["id"]: {"value": []} for g in groups}), groups=True
        )
        with _clear_env():
            self.assertIs(await graph.main(ctx), True)
        flags = {
            g["id"]: g["isPowerBIAudienceGroup"] for g in _saved(ctx)["groups.json"]
        }
        self.assertEqual(
            flags, {"1": True, "2": True, "3": False, "4": False, "5": False}
        )

    async def test_audience_flag_custom_prefixes(self):
        groups = [
            {"id": "1", "displayName": "PowerBI Sales"},
            {"id": "2", "displayName": "Aud-Finance"},
            {"id": "3", "displayName": "REPORT-x"},
        ]
        ctx, _ = _ctx(
            _group_routes(groups, {g["id"]: {"value": []} for g in groups}), groups=True
        )
        with _env(GRAPH_AUDIENCE_GROUP_PREFIXES=" aud- , report- ,"):
            await graph.main(ctx)
        flags = {
            g["id"]: g["isPowerBIAudienceGroup"] for g in _saved(ctx)["groups.json"]
        }
        self.assertEqual(flags, {"1": False, "2": True, "3": True})

    async def test_groupmembers_flat_rows(self):
        groups = [
            {"id": "g1", "displayName": "PowerBI A"},
            {"id": "g2", "displayName": "Other"},
        ]
        members = {
            "g1": {
                "value": [
                    {
                        "id": "m1",
                        "displayName": "M1",
                        "userPrincipalName": "m1@x",
                        "mail": "m1@x",
                        "accountEnabled": True,
                        "userType": "Member",
                    }
                ]
            },
            "g2": {"value": [{"id": "m2"}]},
        }
        ctx, calls = _ctx(_group_routes(groups, members), groups=True)
        with _clear_env():
            self.assertIs(await graph.main(ctx), True)
        rows = _saved(ctx)["groupmembers.json"]
        self.assertEqual(len(rows), 2)
        by_group = {r["groupId"]: r for r in rows}
        self.assertEqual(
            by_group["g1"],
            {
                "groupId": "g1",
                "groupDisplayName": "PowerBI A",
                "isPowerBIAudienceGroup": True,
                "memberId": "m1",
                "displayName": "M1",
                "userPrincipalName": "m1@x",
                "mail": "m1@x",
                "accountEnabled": True,
                "userType": "Member",
            },
        )
        self.assertIs(by_group["g2"]["isPowerBIAudienceGroup"], False)
        self.assertEqual(by_group["g2"]["memberId"], "m2")
        self.assertIsNone(by_group["g2"]["mail"])
        self.assertTrue(
            any("/groups/g1/transitiveMembers/microsoft.graph.user" in c[0] for c in calls)
        )

    async def test_member_pages_are_followed(self):
        groups = [{"id": "g1", "displayName": "A"}]
        pages = [
            {
                "value": [{"id": "m1"}],
                "@odata.nextLink": f"{ROOT}/groups/g1/transitiveMembers/next",
            },
            {"value": [{"id": "m2"}]},
        ]

        async def invoke(rest_api, headers=None, json=None):
            if rest_api.startswith(f"{ROOT}/groups/g1/transitiveMembers"):
                return pages.pop(0)
            if rest_api.startswith(f"{ROOT}/groups?"):
                return {"value": groups}
            return {"value": []}

        ctx = make_context(invoke=invoke)
        ctx.GraphExtractGroups = True
        client = MagicMock()
        client.get_headers.return_value = {}
        client.get_api_root.return_value = ROOT
        ctx.clients["graph"] = client
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual(
            [r["memberId"] for r in _saved(ctx)["groupmembers.json"]], ["m1", "m2"]
        )

    async def test_max_groups_cap(self):
        groups = [{"id": f"g{i}", "displayName": "G"} for i in range(5)]
        members = {g["id"]: {"value": [{"id": "m" + g["id"]}]} for g in groups}
        ctx, calls = _ctx(_group_routes(groups, members), groups=True)
        with _env(GRAPH_MAX_GROUPS_FOR_MEMBERS="2"):
            self.assertIs(await graph.main(ctx), True)
        self.assertEqual(
            sorted(r["groupId"] for r in _saved(ctx)["groupmembers.json"]), ["g0", "g1"]
        )
        self.assertEqual(len([c for c in calls if "/transitiveMembers" in c[0]]), 2)
        self.assertEqual(len(_saved(ctx)["groups.json"]), 5)
        ctx.logger.warning.assert_called()

    async def test_max_groups_zero_fetches_no_members(self):
        groups = [{"id": "g0", "displayName": "G"}]
        ctx, calls = _ctx(_group_routes(groups, {}), groups=True)
        with _env(GRAPH_MAX_GROUPS_FOR_MEMBERS="0"):
            self.assertIs(await graph.main(ctx), True)
        self.assertEqual(_saved(ctx)["groupmembers.json"], [])
        self.assertFalse([c for c in calls if "/transitiveMembers" in c[0]])

    async def test_max_groups_invalid_value_uses_default(self):
        with _env(GRAPH_MAX_GROUPS_FOR_MEMBERS="lots"):
            self.assertEqual(graph.max_groups_for_members(), 200)
        with _env(GRAPH_MAX_GROUPS_FOR_MEMBERS="-5"):
            self.assertEqual(graph.max_groups_for_members(), 0)

    async def test_failed_member_fetch_skips_group_and_returns_false(self):
        groups = [{"id": "g1", "displayName": "A"}, {"id": "g2", "displayName": "B"}]
        members = {"g1": {"ERROR": "403"}, "g2": {"value": [{"id": "m2"}]}}
        ctx, _ = _ctx(_group_routes(groups, members), groups=True)
        self.assertIs(await graph.main(ctx), False)
        saved = _saved(ctx)
        self.assertEqual([r["groupId"] for r in saved["groupmembers.json"]], ["g2"])
        self.assertEqual(len(saved["groups.json"]), 2)
        self.assertIn("users.json", saved)
        ctx.logger.warning.assert_called()

    async def test_member_fetch_exception_skips_group_and_returns_false(self):
        groups = [{"id": "g1", "displayName": "A"}, {"id": "g2", "displayName": "B"}]
        members = {
            "g1": aiohttp.ClientError("boom"),
            "g2": {"value": [{"id": "m2"}]},
        }
        ctx, _ = _ctx(_group_routes(groups, members), groups=True)
        self.assertIs(await graph.main(ctx), False)
        saved = _saved(ctx)
        self.assertEqual([r["groupId"] for r in saved["groupmembers.json"]], ["g2"])
        self.assertEqual(len(saved["groups.json"]), 2)
        self.assertIn("users.json", saved)
        ctx.logger.warning.assert_called()

    async def test_groups_off_still_writes_users_skus_licenses(self):
        users = [
            {
                "id": "u",
                "userPrincipalName": "u@x",
                "assignedLicenses": [{"skuId": "s"}],
            }
        ]
        ctx, calls = _ctx(
            {
                f"{ROOT}/users": {"value": users},
                f"{ROOT}/subscribedSkus": {"value": [{"id": "k"}]},
            }
        )
        self.assertIs(await graph.main(ctx), True)
        saved = _saved(ctx)
        self.assertEqual(
            set(saved), {"users.json", "subscribedskus.json", "userlicenses.json"}
        )
        self.assertFalse([c for c in calls if "/groups" in c[0]])

    async def test_failed_groups_call_skips_members(self):
        ctx, _ = _ctx(
            {
                f"{ROOT}/users": {"value": []},
                f"{ROOT}/subscribedSkus": {"value": []},
                f"{ROOT}/groups": {"ERROR": "x"},
            },
            groups=True,
        )
        self.assertIs(await graph.main(ctx), False)
        saved = _saved(ctx)
        self.assertNotIn("groups.json", saved)
        self.assertNotIn("groupmembers.json", saved)


class ContextGraphExtractGroupsTests(unittest.TestCase):
    def _read(self, **env):
        with patch.dict(os.environ, env):
            if "GRAPH_EXTRACT_GROUPS" not in env:
                os.environ.pop("GRAPH_EXTRACT_GROUPS", None)
            return Context().GraphExtractGroups

    def test_truthy_strings_enable(self):
        for v in ("true", "TRUE", "1", "yes", "On", " true "):
            with self.subTest(v=v):
                self.assertTrue(self._read(GRAPH_EXTRACT_GROUPS=v))

    def test_other_values_disable(self):
        for v in ("", "false", "0", "no", "off", "banana"):
            with self.subTest(v=v):
                self.assertFalse(self._read(GRAPH_EXTRACT_GROUPS=v))

    def test_unset_disables(self):
        self.assertFalse(self._read())


if __name__ == "__main__":
    unittest.main()
