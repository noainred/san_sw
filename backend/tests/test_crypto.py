from backend.app import crypto


def test_roundtrip():
    enc = crypto.encrypt("s3cr3t")
    assert enc.startswith("enc:")
    assert enc != "s3cr3t"
    assert crypto.decrypt(enc) == "s3cr3t"


def test_plaintext_passthrough_for_backcompat():
    # "enc:" 접두어 없으면 평문으로 간주(하위호환)
    assert crypto.decrypt("plain") == "plain"


def test_empty_and_none():
    assert crypto.encrypt(None) is None
    assert crypto.encrypt("") == ""
    assert crypto.decrypt(None) is None


def test_double_encrypt_is_noop():
    enc = crypto.encrypt("x")
    assert crypto.encrypt(enc) == enc  # 이미 암호화된 값은 재암호화하지 않음


def test_is_encrypted():
    assert crypto.is_encrypted(crypto.encrypt("a")) is True
    assert crypto.is_encrypted("plain") is False
