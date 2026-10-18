"""Помощники для текста на русском"""


def plural(n, one, few, many):
    """Склонение по числу: plural(1, 'подход', 'подхода', 'подходов') → 'подход'; 3 → 'подхода'; 5 → 'подходов'"""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
