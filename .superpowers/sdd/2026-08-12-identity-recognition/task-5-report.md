# Task 5 Report — Wire recognition into CameraWorker

## Status
DONE

## Commit hash(es)
bf43f364ef6ec3f4cc5ba8523e0938458c797175

## Test summary
2/2 new tests pass (`test_decide_worker_event_known`, `test_decide_worker_event_intruder`); full suite shows 7 pre-existing failures unrelated to this change (verified by stashing `secur/main.py` — same 7 failures occur without my edits, in `alerts.py` MQTT/HA handler monkeypatches and `app.py` zone routes).

## Concerns
- 7 unrelated tests fail on `dev` before and after my change: `test_alerts.py::test_mqtt_handler_publishes`, `test_alerts.py::test_home_assistant_handler_sends_event`, and 5 `test_zones.py` zone/HA tests. These stem from handler monkeypatch key mismatches (`topic`/`url`) and app zone-route validation (400 instead of 201), none touched by main.py. Recommend separate fix in a later task.
- Added `build_recognizer` to the top-level import (rather than a redundant local import in `main()`) to satisfy the brief's "import it once" note.
