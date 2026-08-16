from src.main import should_send_no_motion


def test_no_motion_requires_reported_motion():
    # Sem movimento检测 algum: não emite.
    assert should_send_no_motion(None, False, False, 100.0, 60.0) is False


def test_no_motion_suppressed_when_only_noise():
    # Detector disparou (last_motion_time set) mas o evento foi suprimido
    # (motion_reported=False): não deve gerar "sem movimento" (regressão do bug).
    assert should_send_no_motion(100.0, False, False, 200.0, 60.0) is False


def test_no_motion_emitted_after_reported_motion_quiet_period():
    assert should_send_no_motion(100.0, True, False, 200.0, 60.0) is True


def test_no_motion_not_yet_quiet_enough():
    assert should_send_no_motion(100.0, True, False, 150.0, 60.0) is False


def test_no_motion_not_repeated_once_alerted():
    assert should_send_no_motion(100.0, True, True, 200.0, 60.0) is False


def test_no_motion_after_firing_reset_reported():
    # Após emitir, motion_reported é zerado e não repete sem novo movimento.
    assert should_send_no_motion(100.0, False, True, 200.0, 60.0) is False
