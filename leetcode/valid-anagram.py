"""LeetCode 242. Valid Anagram.

An anagram uses the same letters the same number of times. "anagram" and
"nagaram" are anagrams. "rat" and "car" are not.

Approach: if the lengths differ, stop. Otherwise keep one array of 26 counts,
one slot per lowercase English letter. Walk both strings together: add one for
a letter in s, subtract one for the letter in t. At the end every slot is zero
exactly when the two strings are anagrams.

The problem statement limits both strings to lowercase English letters, so 26
slots are enough.

Time: O(n). We look at each character once.
Space: O(1). The count array is always 26 long, however long the strings are.
"""

from __future__ import annotations


def is_anagram(s: str, t: str) -> bool:
    if len(s) != len(t):
        return False
    counts = [0] * 26
    for left, right in zip(s, t, strict=True):
        counts[ord(left) - ord("a")] += 1
        counts[ord(right) - ord("a")] -= 1
    return all(count == 0 for count in counts)


if __name__ == "__main__":
    assert is_anagram("anagram", "nagaram") is True
    assert is_anagram("rat", "car") is False
    assert is_anagram("a", "a") is True
    assert is_anagram("ab", "a") is False
    print("is_anagram checks passed")
