import unittest

from fastapi.routing import APIRoute

from app.main import app


class TestAPIContracts(unittest.TestCase):

    def test_every_api_route_has_an_explicit_auth_boundary(self):
        public_or_disabled = {
            ("GET", "/api/auth/linkedin/start"),
            ("GET", "/api/auth/linkedin/callback"),
            ("POST", "/api/auth/linkedin/exchange"),
            ("POST", "/api/auth/linkedin/login"),
            ("POST", "/api/auth/logout"),
            ("POST", "/api/profile"),
            ("POST", "/api/brand/initialize"),
        }
        manually_authenticated = {
            ("GET", "/api/auth/me"),
            ("GET", "/api/linkedin/status"),
            ("POST", "/api/linkedin/profile/sync-missing"),
            ("POST", "/api/internal/scheduled-jobs/{job_name}"),
        }

        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
                continue
            for method in route.methods or set():
                if method in {"HEAD", "OPTIONS"}:
                    continue
                key = (method, route.path)
                if key in public_or_disabled:
                    continue

                dependency_calls = [dependency.call for dependency in route.dependant.dependencies]
                if key in manually_authenticated:
                    if route.path.startswith("/api/internal/"):
                        self.assertTrue(
                            any(getattr(call, "__name__", "") == "_require_scheduled_job_key" for call in dependency_calls),
                            f"Missing scheduled-job secret dependency: {key}",
                        )
                    else:
                        self.assertIn(
                            "request",
                            route.endpoint.__code__.co_varnames,
                            f"Manual authentication route must receive Request: {key}",
                        )
                    continue

                self.assertTrue(
                    any(
                        getattr(call, "__module__", "") == "app.auth"
                        and getattr(call, "__name__", "") == "dependency"
                        for call in dependency_calls
                    ),
                    f"Missing role authorization dependency: {key}",
                )

    def test_documented_routes_have_unique_operation_ids_and_responses(self):
        schema = app.openapi()
        operation_ids = []
        route_count = 0
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.include_in_schema:
                continue
            route_count += 1
            self.assertIn(route.path, schema["paths"])
            for method in route.methods or set():
                if method in {"HEAD", "OPTIONS"}:
                    continue
                operation = schema["paths"][route.path].get(method.lower())
                self.assertIsNotNone(operation, f"Missing OpenAPI operation: {method} {route.path}")
                self.assertTrue(operation.get("operationId"))
                self.assertTrue(operation.get("responses"))
                operation_ids.append(operation["operationId"])
        self.assertGreater(route_count, 40)
        self.assertEqual(len(operation_ids), len(set(operation_ids)))
        self.assertNotIn("/api/account/export", schema["paths"])


if __name__ == "__main__":
    unittest.main()
