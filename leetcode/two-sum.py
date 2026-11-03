"""LeetCode 1. Two Sum.

Approach: one pass with a hash map. For each number, the partner we still need
is target minus that number. If the partner is already in the map, those two
indexes are the answer. Otherwise remember this number's index and keep going.

Time: O(n). We look at each element once, and a dict lookup is O(1) on average.
Space: O(n). The map stores at most one index per element.
"""

from __future__ import annotations


def two_sum(nums: list[int], target: int) -> list[int]:
    seen: dict[int, int] = {}
    for index, num in enumerate(nums):
        need = target - num
        if need in seen:
            return [seen[need], index]
        seen[num] = index
    return []


if __name__ == "__main__":
    assert two_sum([2, 7, 11, 15], 9) == [0, 1]
    assert two_sum([3, 2, 4], 6) == [1, 2]
    assert two_sum([3, 3], 6) == [0, 1]
    print("two_sum checks passed")
