from brain_api.config import Settings


def test_plaintext_yougile_credentials_are_not_runtime_settings():
    fields = Settings.model_fields
    assert "yougile_api_key" not in fields
    assert "yougile_company_id" not in fields
    assert "yougile_project_id" not in fields
