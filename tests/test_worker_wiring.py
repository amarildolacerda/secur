"""Regressão de wiring do worker: decide_worker_event pode retornar None
(supressão fora do horário / sem identidade válida) e o worker não pode
lançar TypeError ao desempacotar a decisão (Fase 3)."""

from src.main import _unpack_worker_decision, decide_worker_event


def test_worker_unpacks_none_outside_schedule():
    # Fora do horário + sem identidade válida → decide_worker_event retorna None
    decision = decide_worker_event(
        [{"label": "person"}], None, "privativa", "Cam",
        label="person", in_schedule=False,
    )
    assert decision is None
    # RED antes do fix: desempacotar None direto lançaria TypeError.
    event_type, details, identity_name, known, _label, category = _unpack_worker_decision(decision)
    assert event_type is None
    assert (details, identity_name, known, _label, category) == (None, None, None, None, None)


def test_worker_unpacks_identity_decision_passthrough():
    identity_info = {"known": True, "name": "Alice"}
    decision = decide_worker_event([], identity_info, "privativa", "Cam",
                                   label="person", in_schedule=False)
    assert decision is not None
    event_type, details, identity_name, known, _label, category = _unpack_worker_decision(decision)
    assert event_type == "identity_recognized"
    assert identity_name == "Alice" and known is True


def test_worker_unpacks_motion_decision_passthrough():
    decision = decide_worker_event([], None, "pública", "Cam", in_schedule=True)
    assert decision is not None
    event_type, details, *_ = _unpack_worker_decision(decision)
    assert event_type == "motion_detected"
    assert details and "Movimento" in details
