import unittest

from app.db.models import CredentialType
from app.services.llm_service import LLM_REQUEST_TIMEOUT, LLMService


class LLMRequestTimeoutTest(unittest.TestCase):
    """The per-node request timeout must reach the underlying OpenAI client."""

    def test_default_request_timeout_matches_module_constant(self) -> None:
        service = LLMService(CredentialType.openai, "sk-test")
        client, label = service._get_client()
        self.assertEqual(client.timeout, LLM_REQUEST_TIMEOUT)
        self.assertEqual(label, "OpenAI")

    def test_openai_client_uses_custom_request_timeout(self) -> None:
        service = LLMService(CredentialType.openai, "sk-test", request_timeout=300.0)
        client, label = service._get_client()
        self.assertEqual(client.timeout, 300.0)
        self.assertEqual(label, "OpenAI")

    def test_custom_provider_client_uses_custom_request_timeout(self) -> None:
        service = LLMService(
            CredentialType.custom,
            "sk-test",
            base_url="https://litellm.example.com",
            request_timeout=300.0,
        )
        client, label = service._get_client()
        self.assertEqual(client.timeout, 300.0)
        self.assertEqual(label, "Custom")

    def test_google_client_uses_custom_request_timeout(self) -> None:
        service = LLMService(CredentialType.google, "sk-test", request_timeout=300.0)
        client, label = service._get_client()
        self.assertEqual(client.timeout, 300.0)
        self.assertEqual(label, "Google")


if __name__ == "__main__":
    unittest.main()
