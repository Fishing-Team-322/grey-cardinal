from brain_api.infrastructure.security.encryption import SecretCipher


def test_board_credentials_encryption():
    cipher = SecretCipher("unit-test-secret")
    encrypted = cipher.encrypt_text('{"api_key":"secret"}')

    assert b"secret" not in encrypted
    assert cipher.decrypt_text(encrypted) == '{"api_key":"secret"}'
