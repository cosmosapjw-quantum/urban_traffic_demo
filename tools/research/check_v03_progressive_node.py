"""Exact finite checks of the progressive node capacity/composition certificate."""
from fractions import Fraction as F
from itertools import combinations, product


H = ((1, 1, 0), (0, 1, 1), (1, 0, 0), (0, 2, 0), (0, 0, 1))


def fill(matrix, capacities, threshold=0):
    active = set(range(len(matrix[0])))
    levels = [F(0)] * len(matrix[0])
    tightened = list(capacities)
    while active:
        slopes = [sum(row[i] for i in active) for row in matrix]
        level = min(
            (bound - sum(coeff * levels[i] for i, coeff in enumerate(row) if i not in active))
            / slope
            for row, bound, slope in zip(matrix, capacities, slopes)
            if slope
        )
        for i in active:
            levels[i] = level
        stop = set()
        for j, (row, bound, slope) in enumerate(zip(matrix, capacities, slopes)):
            used = sum(coeff * value for coeff, value in zip(row, levels))
            if slope and bound - used <= threshold:
                stop.update(i for i in active if row[i])
                tightened[j] = used
        assert stop
        active -= stop
    return tuple(levels), tuple(tightened)


def certify(matrix, capacities, levels):
    used = tuple(sum(coeff * value for coeff, value in zip(row, levels)) for row in matrix)
    assert all(actual <= bound for actual, bound in zip(used, capacities))
    for i, level in enumerate(levels):
        assert any(
            row[i] and actual == bound
            and all(not coeff or candidate <= level for coeff, candidate in zip(row, levels))
            for row, actual, bound in zip(matrix, used, capacities)
        )


def main():
    epsilon = F(1, 1000)
    for left, right, expected in (
        (2 - epsilon, 2 + epsilon, (1 - epsilon / 2, 1 - epsilon / 2, 1 + 3 * epsilon / 2)),
        (F(2), F(2), (1, 1, 1)),
        (2 + epsilon, 2 - epsilon, (1 + 3 * epsilon / 2, 1 - epsilon / 2, 1 - epsilon / 2)),
    ):
        capacities = tuple(map(F, (left, right, 10, 20, 10)))
        levels, _ = fill(H, capacities)
        certify(H, capacities, levels)
        assert levels == expected
        print("receiving", left, right, "normalized rates", *(str(value) for value in levels))
    grid = [tuple(map(F, (left, right, 10, 20, 10))) for left, right in product(range(5), repeat=2)]
    solutions = {capacities: fill(H, capacities)[0] for capacities in grid}
    pair_count = 0
    for left, right in combinations(grid, 2):
        error = max(abs(a - b) for a, b in zip(solutions[left], solutions[right]))
        capacity_delta = max(abs(a - b) for a, b in zip(left, right))
        assert error <= F(3, 2) * capacity_delta
        pair_count += 1
    composition_grid = list(product((F(0), F(1, 2), F(2), F(4)), repeat=5))
    changed_matrix = ((1, F(6, 5), 0), (0, F(4, 5), 1), *H[2:])
    for capacities in composition_grid:
        levels, _ = fill(H, capacities)
        certify(H, capacities, levels)
        shifted = tuple(
            bound + sum((new - old) * level for new, old, level in zip(new_row, old_row, levels))
            for bound, new_row, old_row in zip(capacities, changed_matrix, H)
        )
        assert fill(changed_matrix, shifted)[0] == levels
        threshold = F(3, 5)
        early_levels, adjusted = fill(H, capacities, threshold)
        certify(H, adjusted, early_levels)
        assert all(0 <= bound - reduced <= threshold for bound, reduced in zip(capacities, adjusted))
        assert fill(H, adjusted)[0] == early_levels
    print("exact capacity pairs:", pair_count, "composition and backward tolerance cases:", len(composition_grid))


if __name__ == "__main__":
    main()
