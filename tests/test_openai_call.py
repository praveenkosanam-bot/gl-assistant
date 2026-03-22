import importlib
import sys
import types
import unittest
from unittest import mock


class DummyPool:
    def acquire(self):
        raise AssertionError("Database access is not expected in this unit test")


def import_app_module():
    class FakeFlask:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def get(self, *args, **kwargs):
            return self.route(*args, **kwargs)

        def post(self, *args, **kwargs):
            return self.route(*args, **kwargs)

    fake_oracledb = types.SimpleNamespace(
        create_pool=lambda **kwargs: DummyPool(),
        DB_TYPE_NUMBER=object(),
    )
    fake_requests = types.SimpleNamespace(
        Session=lambda: None,
        RequestException=Exception,
    )
    fake_yaml = types.SimpleNamespace(safe_load=lambda text: {})
    fake_flask = types.SimpleNamespace(
        Flask=FakeFlask,
        jsonify=lambda *args, **kwargs: {"args": args, "kwargs": kwargs},
        render_template=lambda *args, **kwargs: "",
        request=types.SimpleNamespace(get_json=lambda silent=False: None),
    )
    sys.modules["oracledb"] = fake_oracledb
    sys.modules["requests"] = fake_requests
    sys.modules["yaml"] = fake_yaml
    sys.modules["flask"] = fake_flask
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class ResolveQuestionWithLlmTests(unittest.TestCase):
    def test_openai_responses_call_routes_question(self):
        app_module = import_app_module()
        app_module.MOCK_OPENAI = False
        app_module.OPENAI_API_KEY = "test-key"

        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "output_text": '{"api_path":"/api/db/balance/by-account","params":{"account_number":"1000","ledger_id":101,"period_name":"JAN-24"}}'
        }

        fake_session = mock.Mock()
        fake_session.post.return_value = fake_response

        with mock.patch.object(app_module.requests, "Session", return_value=fake_session):
            routed = app_module.resolve_question_with_llm(
                history=[{"role": "user", "content": "Show me the balance for account 1000"}],
                question="What is the balance for account 1000 in JAN-24 for ledger 101?",
            )

        self.assertEqual(routed["api_path"], "/api/db/balance/by-account")
        self.assertEqual(routed["params"]["account_number"], "1000")
        self.assertEqual(routed["params"]["ledger_id"], 101)
        self.assertEqual(routed["params"]["period_name"], "JAN-24")
        self.assertEqual(routed["params"]["actual_flag"], "A")
        self.assertFalse(routed["params"]["resolved_from_seed"])
        self.assertEqual(routed["routing_mode"], "openai")

        self.assertFalse(fake_session.trust_env)
        fake_session.post.assert_called_once()
        _, kwargs = fake_session.post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["json"]["model"], app_module.OPENAI_MODEL)
        self.assertEqual(kwargs["json"]["instructions"], app_module.SYSTEM_PROMPT)
        self.assertEqual(kwargs["timeout"], 60)
        self.assertEqual(kwargs["json"]["input"][0]["content"][0]["type"], "input_text")
        self.assertIn("Latest user question", kwargs["json"]["input"][0]["content"][0]["text"])

    def test_openai_route_backfills_ledger_and_period_from_question(self):
        app_module = import_app_module()
        app_module.MOCK_OPENAI = False
        app_module.OPENAI_API_KEY = "test-key"

        fake_response = mock.Mock()
        fake_response.json.return_value = {
            "output_text": '{"api_path":"/api/db/balance/by-account","params":{"account_number":"1000"}}'
        }

        fake_session = mock.Mock()
        fake_session.post.return_value = fake_response

        with mock.patch.object(app_module.requests, "Session", return_value=fake_session):
            routed = app_module.resolve_question_with_llm(
                history=[],
                question="What is the balance for account 1000 in JAN-24 for ledger 101?",
            )

        self.assertEqual(routed["api_path"], "/api/db/balance/by-account")
        self.assertEqual(routed["params"]["account_number"], "1000")
        self.assertEqual(routed["params"]["ledger_id"], 101)
        self.assertEqual(routed["params"]["period_name"], "JAN-24")


class RouteValidationTests(unittest.TestCase):
    def test_validate_route_params_reports_missing_fields(self):
        app_module = import_app_module()
        error = app_module.validate_route_params("/api/db/balance/by-account", {"account_number": "1000"})
        self.assertEqual(error, "Missing required query inputs: ledger_id, period_name")


class ParsingDefaultsTests(unittest.TestCase):
    def test_extract_filters_treats_bare_number_as_account(self):
        app_module = import_app_module()
        parsed = app_module.extract_filters("whats the balance of 12300 for period 01-23")
        self.assertEqual(parsed["account_number"], "12300")
        self.assertEqual(parsed["period_name"], "01-23")

    def test_complete_lookup_params_defaults_to_us_primary_ledger(self):
        app_module = import_app_module()
        completed = app_module.complete_lookup_params(
            "whats the balance of 12300 for period 01-23",
            {"account_number": "12300", "period_name": "01-23"},
        )
        self.assertEqual(completed["ledger_id"], app_module.DEFAULT_LEDGER_ID)
        self.assertEqual(completed["period_name"], "01-23")
        self.assertEqual(completed["account_number"], "12300")


if __name__ == "__main__":
    unittest.main()
