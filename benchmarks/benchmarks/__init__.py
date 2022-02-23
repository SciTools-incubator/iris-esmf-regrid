"""Benchmark tests for iris-esmf-regrid"""


def disable_repeat_between_setup(benchmark_object):
    """
    Decorator for benchmarks where object persistence would be inappropriate.

    E.g:
        * Data is realised during testing.

    Can be applied to benchmark classes/methods/functions.

    https://asv.readthedocs.io/en/stable/benchmarks.html#timing-benchmarks

    """
    # Prevent repeat runs between setup() runs - object(s) will persist after 1st.
    benchmark_object.number = 1
    # Compensate for reduced certainty by increasing number of repeats.
    #  (setup() is run between each repeat).
    #  Minimum 5 repeats, run up to 30 repeats / 20 secs whichever comes first.
    benchmark_object.repeat = (5, 30, 20.0)
    # ASV uses warmup to estimate benchmark time before planning the real run.
    #  Prevent this, since object(s) will persist after first warmup run,
    #  which would give ASV misleading info (warmups ignore ``number``).
    benchmark_object.warmup_time = 0.0

    return benchmark_object


def skip_benchmark(benchmark_object):
    """
    Decorator for benchmarks skipping benchmarks.
    """

    def setup_cache(self):
        pass

    def setup(*args):
        raise NotImplementedError

    benchmark_object.setup_cache = setup_cache
    benchmark_object.setup = setup

    return benchmark_object
