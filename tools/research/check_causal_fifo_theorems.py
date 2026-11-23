"""Exact-rational checks for a source-aligned FIFO mass-coordinate adapter.

Temporary research artifact for parent integration; no production V03 claim.
Run: python rank_fifo_proposal_checks.py
"""
from dataclasses import dataclass
from fractions import Fraction as F
import itertools
import json
import random


@dataclass(frozen=True)
class UniformHead:
    # Same sequence/keys as one existing PacketParts; birth is a first moment.
    masses: tuple[F, ...]
    births: tuple[F, ...]
    consumed: F = F(0)

    def __post_init__(self):
        if len(self.masses) != len(self.births) or not self.masses:
            raise ValueError("source shape")
        if any(x <= 0 for x in self.masses) or any(x < 0 for x in self.births):
            raise ValueError("source moments")
        if not 0 <= self.consumed <= self.total:
            raise ValueError("rank cursor outside source")

    @property
    def total(self):
        return sum(self.masses, F(0))

    @property
    def remaining(self):
        return self.total - self.consumed

    def take(self, amount, eligible):
        # eligible is an absolute mass-rank frontier in this source block.
        amount, eligible = F(amount), F(eligible)
        if not self.consumed <= eligible <= self.total:
            raise ValueError("noncausal eligibility")
        if not 0 <= amount <= eligible - self.consumed:
            raise ValueError("service exceeds causal eligible frontier")
        frac = amount / self.total
        served = (tuple(x * frac for x in self.masses),
                  tuple(x * frac for x in self.births))
        return UniformHead(self.masses, self.births, self.consumed + amount), served


def exact_source_split_checks():
    rng = random.Random(2691)
    cases = 0
    for nrows in (1, 2, 7, 31):
        for _ in range(30):
            masses = tuple(F(rng.randint(1, 99), 17) for _ in range(nrows))
            births = tuple(m * F(rng.randint(0, 60), 3) for m in masses)
            head = UniformHead(masses, births)
            original_masses = masses
            original_births = births
            eager_masses, eager_births = list(masses), list(births)
            emitted_masses = [F(0)] * nrows
            emitted_births = [F(0)] * nrows
            for k in range(25):
                fraction = F(rng.randint(1, 9), 10) if k < 24 else F(1)
                amount = sum(eager_masses, F(0)) * fraction
                nxt, (served_masses, served_births) = head.take(amount, head.total)
                assert nxt.masses is original_masses and nxt.births is original_births
                for i in range(nrows):
                    assert served_masses[i] == eager_masses[i] * fraction
                    assert served_births[i] == eager_births[i] * fraction
                    eager_masses[i] *= 1 - fraction
                    eager_births[i] *= 1 - fraction
                    emitted_masses[i] += served_masses[i]
                    emitted_births[i] += served_births[i]
                    assert eager_masses[i] == original_masses[i] * nxt.remaining / nxt.total
                    assert eager_births[i] == original_births[i] * nxt.remaining / nxt.total
                head = nxt
                cases += 1
            assert emitted_masses == list(masses)
            assert emitted_births == list(births)
            assert head.remaining == 0
    # A real finite-speed boundary, including a stopped eligibility frontier.
    h = UniformHead((F(2), F(3)), (F(4), F(15)))
    h, _ = h.take(2, 2)
    try:
        h.take(1, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("service passed stopped frontier")
    assert h.take(3, 5)[0].remaining == 0
    return cases


def conservative_rank_closure_checks():
    # Every binary commodity sequence on equal-volume atoms, all cuts. This
    # finite computation complements the general measurable-profile proof.
    prefix_checks = 0
    sharp_witness = None
    for n in range(1, 11):
        h = F(n)
        for seq in itertools.product((0, 1), repeat=n):
            p = F(sum(seq), n)
            for k in range(n + 1):
                actual = F(sum(seq[:k]))
                linear = p * k
                error = abs(actual - linear)
                assert error <= h * p * (1 - p) <= h / 4
                assert max(F(0), h * p - (h - k)) <= actual <= min(h * p, F(k))
                if error == h / 4 and h > 0:
                    sharp_witness = {"profile": list(seq), "mass": str(h),
                                     "cut": k, "error": str(error)}
                prefix_checks += 1
    return prefix_checks, sharp_witness


if __name__ == "__main__":
    source_checks = exact_source_split_checks()
    prefix_checks, witness = conservative_rank_closure_checks()
    print(json.dumps({
        "source_split_equalities_checked": source_checks,
        "exact_prefix_bound_checks": prefix_checks,
        "sharp_bound_witness": witness,
        "source_storage_copied_on_service": False,
        "causal_eligibility_negative_control": "REJECTED_AS_EXPECTED",
        "scope": "exact rational single-head adapter; closure bound for scalar commodity prefix",
        "production_V03": "NOT_INTEGRATED",
    }, indent=2))
