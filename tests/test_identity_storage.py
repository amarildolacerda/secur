import numpy as np
from secur.storage import EventStorage


def test_known_identities_crud(tmp_path, monkeypatch):
    import secur.config as cfg
    monkeypatch.setattr(cfg, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")
    (tmp_path / "emb").mkdir(exist_ok=True)
    from secur import storage as storage_mod
    monkeypatch.setattr(storage_mod, "IDENTITY_EMBEDDINGS_DIR", tmp_path / "emb")

    db = EventStorage(tmp_path / "events.db")
    emb = np.random.rand(128).astype(np.float32)
    path = db.save_identity_embedding("João", emb)
    assert (tmp_path / "emb" / path.split("/")[-1]).exists()

    ident_id = db.add_identity("João", "person", path)
    loaded = db.load_identity_embedding(ident_id)
    assert loaded is not None and loaded.shape == (128,)

    rows = db.list_identities()
    assert len(rows) == 1 and rows[0]["name"] == "João" and rows[0]["species"] == "person"

    assert db.remove_identity(ident_id) is True
    assert db.list_identities() == []
    db.close()
