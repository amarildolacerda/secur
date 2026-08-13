from secur import config


def test_identity_config_defaults():
    assert config.IDENTITY_ENABLED is False
    assert config.IDENTITY_MATCH_THRESHOLD == 0.6
    assert config.IDENTITY_FACE_MODEL_PATH == ""
    assert config.IDENTITY_REID_MODEL_PATH == ""
    assert config.IDENTITY_EMBEDDINGS_DIR.exists()
