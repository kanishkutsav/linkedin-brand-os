import unittest

from fastapi.routing import APIRoute

from app.main import app


class TestAPIContracts(unittest.TestCase):
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
