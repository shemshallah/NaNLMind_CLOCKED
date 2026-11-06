import json
import unittest
from unittest.mock import patch

from client import endpoint_from_env, make_request


class ParticipantClientTests(unittest.TestCase):
    def test_https_endpoint_required_outside_localhost(self):
        with patch.dict("os.environ", {"CLOCKED_INTAKE_URL": "http://example.test/v1/experience"}):
            with self.assertRaises(ValueError):
                endpoint_from_env()

    def test_localhost_http_is_allowed_for_development(self):
        with patch.dict("os.environ", {"CLOCKED_INTAKE_URL": "http://127.0.0.1:8787/v1/experience"}):
            self.assertEqual(endpoint_from_env(), "http://127.0.0.1:8787/v1/experience")

    def test_request_uses_gateway_token_and_versioned_payload(self):
        request = make_request("https://demo.example/v1/experience", "clu_test", "hello")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer clu_test")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {
            "protocol": "nanlm.clocked-experience", "text": "hello"
        })

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            make_request("https://demo.example/v1/experience", "clu_test", "  ")


if __name__ == "__main__":
    unittest.main()
