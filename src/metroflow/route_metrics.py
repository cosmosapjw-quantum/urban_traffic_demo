"""Optional bounded route-request timing, independent of simulation state.

The nearest-rank p99 is enclosed by integer-nanosecond histogram bounds.
No midpoint estimate is reported as an exact quantile. Up to 64-bit durations,
bins retain eight significant binary digits (width / lower <= 1/128).
"""
from contextvars import ContextVar
from functools import wraps
from time import perf_counter_ns


_observer = ContextVar('metroflow_route_latency_observer', default=None)
_inside_route = ContextVar('metroflow_inside_route_latency', default=False)
_APIS = ('candidate_paths', 'legal_route_cache.resolve',
         'release_runtime.path', 'release_services.path')
_OVERFLOW = 256 + 56 * 128
_BUCKETS = _OVERFLOW + 1


class RouteLatencyMeasurements:
    """Collect outermost registered path API calls in the current context.

    Cache hits and unsuccessful/raising requests count when the caller invokes
    the API. No route lookup is invented for internally handled trips. Nested
    path APIs count once, at the outer boundary. Recording overhead is outside
    the timed interval; timer overhead is not subtracted. A fresh instance is
    used for each single-process campaign worker.
    """
    def __init__(self):
        self.counts = [0] * _BUCKETS
        self.calls_by_api = dict.fromkeys(_APIS, 0)
        self.failed_calls = 0
        self.minimum_ns = None
        self.maximum_ns = None
        self._token = None

    def __enter__(self):
        if self._token is not None:
            raise ValueError('route measurement context is already active')
        self._token = _observer.set(self)
        return self

    def __exit__(self, *exc):
        _observer.reset(self._token)
        self._token = None

    def record_ns(self, duration_ns, api, *, failed=False):
        if (isinstance(duration_ns, bool) or not isinstance(duration_ns, int)
                or duration_ns < 0 or api not in self.calls_by_api):
            raise ValueError('nonnegative integer nanoseconds and registered route API required')
        if duration_ns < 256:
            index = duration_ns
        elif duration_ns >= 1 << 64:
            index = _OVERFLOW
        else:
            shift = duration_ns.bit_length() - 8
            index = 256 + (shift - 1) * 128 + (duration_ns >> shift) - 128
        self.counts[index] += 1
        self.calls_by_api[api] += 1
        self.failed_calls += int(failed)
        self.minimum_ns = duration_ns if self.minimum_ns is None else min(self.minimum_ns, duration_ns)
        self.maximum_ns = duration_ns if self.maximum_ns is None else max(self.maximum_ns, duration_ns)

    def report(self):
        count = sum(self.calls_by_api.values())
        interval = None
        if count:
            # Nearest rank: ceil(0.99*N), evaluated exactly as integers.
            rank = (99 * count + 99) // 100
            cumulative = 0
            for index, frequency in enumerate(self.counts):
                cumulative += frequency
                if cumulative >= rank:
                    break
            if index < 256:
                lower = upper = index
            elif index == _OVERFLOW:
                lower, upper = 1 << 64, self.maximum_ns
            else:
                shift, offset = divmod(index - 256, 128)
                shift += 1
                lower = (128 + offset) << shift
                upper = ((129 + offset) << shift) - 1
            interval = dict(lower=max(lower, self.minimum_ns),
                            upper=min(upper, self.maximum_ns))
        return dict(
            status='MEASURED_INTERVAL' if count else 'NOT_MEASURED',
            observed_calls=count, failed_calls=self.failed_calls,
            calls_by_api=dict(self.calls_by_api), p99_ns=interval,
            quantile='nearest rank ceil(0.99 * observed_calls), including failed requests',
            min_ns=self.minimum_ns, max_ns=self.maximum_ns,
            histogram_bins=_BUCKETS, overflow_samples=self.counts[_OVERFLOW],
            nonsaturated_relative_bin_width_bound=1 / 128,
            clock='perf_counter_ns; timer overhead not subtracted',
            scope='outermost route API calls in this worker, including preparation and invoked cache hits; excludes access-law compilation and physical travel time',
        )


def measure_route_latency(api):
    """Time a registered path API only inside an active measurement context."""
    if api not in _APIS:
        raise ValueError('unknown route latency API')

    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            observer = _observer.get()
            if observer is None or _inside_route.get():
                return function(*args, **kwargs)
            token = _inside_route.set(True)
            started = perf_counter_ns()
            failed = True
            try:
                result = function(*args, **kwargs)
                failed = False
                return result
            finally:
                duration = perf_counter_ns() - started
                _inside_route.reset(token)
                observer.record_ns(duration, api, failed=failed)
        return measured
    return decorate
