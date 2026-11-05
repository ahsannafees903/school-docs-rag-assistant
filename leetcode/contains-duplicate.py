"""LeetCode 217. Contains Duplicate.

Given an integer array, return true if any value appears at least twice.

Approach: one pass with a set. If the number is already in the set, it is a
duplicate and we can stop. Otherwise remember it and keep going.

Time: O(n). We look at each element once, and a set lookup is O(1) on average.
Space: O(n). The set stores each distinct number.
"""

from __future__ import annotations


def contains_duplicate(nums: list[int]) -> bool:
    seen: set[int] = set()
    for num in nums:
        if num in seen:
            return True
        seen.add(num)
    return False


if __name__ == "__main__":
    assert contains_duplicate([1, 2, 3, 1]) is True
    assert contains_duplicate([1, 2, 3, 4]) is False
    assert contains_duplicate([1, 1, 1, 3, 3, 4, 3, 2, 4, 2]) is True
    assert contains_duplicate([]) is False
    assert contains_duplicate([1]) is False
    print("contains_duplicate checks passed")
