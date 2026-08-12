# Task 4 — Fix Report: test_alerts_identity.py

## Status: DONE

## Commit
- `007038364e96f0f65212de71317a732b156fefcf` (branch `dev`)
  - message: `test(alerts): exercise real handlers instead of mirror helpers`
  - only `tests/test_alerts_identity.py` changed.

## Adaptation note
The provided test template's `home_assistant_handler` fake `post` did not accept the
`headers=` keyword argument that the real handler passes at `secur/alerts.py:143`
(`requests.post(event_url, headers=headers, json=payload, timeout=(3, 5))`).
The original `fake_post` signature `(url, data=None, timeout=None, json=None)` raised
a `TypeError` that the handler swallowed via its broad `except Exception`, so `calls`
was never populated and the test failed.

Fix: added `**kwargs` to the HA `fake_post` signature so it accepts `headers`. No change
required to `telegram_handler`/`mqtt_handler` tests. `secur/alerts.py` was NOT modified.

## Verification
`py -3.14 -m pytest tests/test_alerts_identity.py -v` → 3 passed:
- `test_telegram_skips_known_unknown_and_snapshot` — real `telegram_handler` invoked with
  `requests.post` monkeypatched; confirms skip of snapshot_info/identity_recognized/unknown_detected
  and alarm on intruder_detected/motion_detected.
- `test_mqtt_only_intruder` — real `mqtt_handler` invoked with `paho.mqtt.client.Client`
  monkeypatched; confirms publish only on intruder_detected (not identity/unknown).
- `test_ha_receives_all_identity_events` — real `home_assistant_handler` invoked; confirms
  HA receives identity_recognized/intruder_detected/unknown_detected and private motion,
  and skips snapshot_info and public motion.
