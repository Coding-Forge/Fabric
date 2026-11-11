"""B12/B15: refresh history failure return, 404 skip and single save after the loop."""
import unittest
from unittest.mock import MagicMock

from env.modules import refreshhistory
from tests.helpers import make_context


def _ds(ds_id, refreshable=True, add_rows=False):
    return {"id": ds_id, "name": f"name-{ds_id}", "isRefreshable": refreshable, "addRowsAPIEnabled": add_rows}


def _groups(*workspaces):
    return {"value": list(workspaces)}


def _ws(ws_id, *datasets):
    return {"id": ws_id, "name": f"ws-{ws_id}", "datasets": list(datasets)}


def _ctx(routes):
    """``routes`` maps a rest_api string to a response (or a list of responses)."""
    calls = []

    async def invoke(rest_api, headers=None, json=None):
        calls.append(rest_api)
        return routes[rest_api]

    ctx = make_context(invoke=invoke)
    ctx.clients["tenant"] = MagicMock()
    ctx.clients["tenant"].get_headers.return_value = {"Authorization": "x"}
    return ctx, calls


LIST_API = "admin/groups?$expand=datasets&$top=5000"


def _refresh_api(ws, ds):
    return f"groups/{ws}/datasets/{ds}/refreshes"


class RefreshHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await refreshhistory.main(None)

    async def test_workspace_list_failure_returns_false_without_saving(self):
        for bad in (None, {}, {"ERROR": "x"}):
            ctx, _ = _ctx({LIST_API: bad})
            self.assertIs(await refreshhistory.main(ctx), False)
            ctx.fm.save.assert_not_awaited()
            ctx.logger.error.assert_called()

    async def test_success_saves_once_after_loop_with_annotations(self):
        routes = {
            LIST_API: _groups(_ws("w1", _ds("d1"), _ds("d2")), _ws("w2", _ds("d3"))),
            _refresh_api("w1", "d1"): {"value": [{"status": "Completed"}, {"status": "Failed"}]},
            _refresh_api("w1", "d2"): {"value": [{"status": "Completed"}]},
            _refresh_api("w2", "d3"): {"value": [{"status": "Completed"}]},
        }
        ctx, _ = _ctx(routes)
        self.assertIs(await refreshhistory.main(ctx), True)
        # B15: exactly one save, containing every refresh from every dataset
        self.assertEqual(ctx.fm.save.await_count, 1)
        content = ctx.fm.save.await_args.kwargs["content"]
        self.assertEqual(len(content), 4)
        self.assertEqual(ctx.fm.save.await_args.kwargs["file_name"], "workspaces.datasets.refreshes.json")
        self.assertTrue(ctx.fm.save.await_args.kwargs["path"].startswith("datasetrefresh/"))
        first = content[0]
        self.assertEqual((first["workspace_id"], first["workspace_name"]), ("w1", "ws-w1"))
        self.assertEqual((first["dataset_id"], first["dataset_name"]), ("d1", "name-d1"))
        self.assertEqual(content[-1]["dataset_id"], "d3")

    async def test_404_is_skipped_and_not_a_failure(self):
        routes = {
            LIST_API: _groups(_ws("w1", _ds("d1"), _ds("d2"))),
            _refresh_api("w1", "d1"): {"ERROR": "not found", "status": 404},
            _refresh_api("w1", "d2"): {"value": [{"status": "Completed"}]},
        }
        ctx, _ = _ctx(routes)
        self.assertIs(await refreshhistory.main(ctx), True)
        content = ctx.fm.save.await_args.kwargs["content"]
        self.assertEqual([r["dataset_id"] for r in content], ["d2"])
        ctx.logger.error.assert_not_called()

    async def test_non_404_failure_returns_false_but_keeps_other_results(self):
        routes = {
            LIST_API: _groups(_ws("w1", _ds("d1"), _ds("d2"), _ds("d3"))),
            _refresh_api("w1", "d1"): {"ERROR": "throttled", "status": 429},
            _refresh_api("w1", "d2"): {"value": [{"status": "Completed"}]},
            _refresh_api("w1", "d3"): None,
        }
        ctx, _ = _ctx(routes)
        self.assertIs(await refreshhistory.main(ctx), False)
        self.assertEqual(ctx.fm.save.await_count, 1)
        self.assertEqual([r["dataset_id"] for r in ctx.fm.save.await_args.kwargs["content"]], ["d2"])
        self.assertEqual(ctx.logger.error.call_count, 2)

    async def test_only_refreshable_non_addrows_datasets_are_queried(self):
        routes = {
            LIST_API: _groups(_ws("w1", _ds("skip1", refreshable=False), _ds("skip2", add_rows=True), _ds("ok"))),
            _refresh_api("w1", "ok"): {"value": [{"status": "Completed"}]},
        }
        ctx, calls = _ctx(routes)
        self.assertIs(await refreshhistory.main(ctx), True)
        self.assertEqual(calls, [LIST_API, _refresh_api("w1", "ok")])

    async def test_empty_refresh_entries_are_ignored(self):
        routes = {
            LIST_API: _groups(_ws("w1", _ds("d1"))),
            _refresh_api("w1", "d1"): {"value": [{}, {"status": "Completed"}]},
        }
        ctx, _ = _ctx(routes)
        await refreshhistory.main(ctx)
        self.assertEqual(len(ctx.fm.save.await_args.kwargs["content"]), 1)

    async def test_no_workspaces_still_saves_once_and_succeeds(self):
        ctx, _ = _ctx({LIST_API: {"value": [{"id": "w"}]}})
        # a non-empty dict without ERROR; no datasets in the workspace
        self.assertIs(await refreshhistory.main(ctx), True)
        self.assertEqual(ctx.fm.save.await_count, 1)


if __name__ == "__main__":
    unittest.main()
