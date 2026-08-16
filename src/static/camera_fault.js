(function (global, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    global.CameraFault = api;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const FAULT_DEFAULTS = {
    retryIntervalMs: 15000,
    offlineRetryIntervalMs: 30000,
    offlineThresholdMs: 300000,
  };

  function transitionFault(state, event, now, cfg) {
    const c = Object.assign({}, FAULT_DEFAULTS, cfg || {});
    if (event === 'load') {
      return { state: null, reload: false, offline: false };
    }
    const prev = state || { status: 'retrying', firstFailAt: now, timer: null };
    if (prev.status === 'retrying' && (now - prev.firstFailAt) >= c.offlineThresholdMs) {
      return {
        state: { status: 'offline', firstFailAt: prev.firstFailAt, timer: null },
        reload: true,
        offline: true,
      };
    }
    return {
      state: { status: prev.status, firstFailAt: prev.firstFailAt, timer: null },
      reload: true,
      offline: false,
    };
  }

  function nextRetryIntervalMs(state, cfg) {
    const c = Object.assign({}, FAULT_DEFAULTS, cfg || {});
    if (state && state.status === 'offline') return c.offlineRetryIntervalMs;
    return c.retryIntervalMs;
  }

  return { FAULT_DEFAULTS, transitionFault, nextRetryIntervalMs };
});
