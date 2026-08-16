import src.status as status


def test_build_includes_all_groups(monkeypatch):
    monkeypatch.setattr(status, "_probe_telegram", lambda t: (True, "ok"))
    monkeypatch.setattr(status, "_probe_mqtt", lambda b, p: (False, "sem broker"))
    monkeypatch.setattr(status, "_probe_ha", lambda u, t: (False, "sem HA"))
    out = status.build_system_status(camera_manager=None)
    groups = [m["group"] for m in out["modules"]]
    assert groups == ["Captura", "Detecção", "Identidade", "Notificações"]
    workers = out["modules"][0]["items"][1]
    assert workers["configured"] is False
    tg = out["modules"][3]["items"][0]
    assert tg["operational"] is True


def test_detector_configured_when_path_exists(tmp_path, monkeypatch):
    model = tmp_path / "m.onnx"
    model.write_bytes(b"fake")
    monkeypatch.setattr(status, "DETECTOR_MODEL_PATH", str(model))
    monkeypatch.setattr(status, "_probe_telegram", lambda t: (False, "x"))
    monkeypatch.setattr(status, "_probe_mqtt", lambda b, p: (False, "x"))
    monkeypatch.setattr(status, "_probe_ha", lambda u, t: (False, "x"))
    out = status.build_system_status()
    det = out["modules"][1]["items"][1]
    assert det["configured"] is True
    assert det["operational"] is False
    assert "falha" in det["detail"].lower()
