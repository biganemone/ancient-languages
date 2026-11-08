"""Python twin of app/AncientLanguages/Study/FSRS.swift, for checking the numbers.

Run: python fsrs_check.py   (prints a few review histories and asserts sanity)
"""
import math

W = [0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796,
     1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542]
AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
RETENTION = 0.9
DECAY = -W[20]
FACTOR = 0.9 ** (1 / DECAY) - 1


def R(t, s):
    return (1 + FACTOR * max(t, 0) / s) ** DECAY


def interval(s):
    return min(max(round(s / FACTOR * (RETENTION ** (1 / DECAY) - 1)), 1), 36500)


def clamp(d):
    return min(max(d, 1), 10)


def D0(g):
    return clamp(W[4] - math.exp(W[5] * (g - 1)) + 1)


def next_d(d, g):
    damped = d + (-W[6] * (g - 3)) * (10 - d) / 9
    return clamp(W[7] * D0(EASY) + (1 - W[7]) * damped)


def recall_s(d, s, r, g):
    return s * (math.exp(W[8]) * (11 - d) * s ** -W[9] * (math.exp(W[10] * (1 - r)) - 1)
                * (W[15] if g == HARD else 1) * (W[16] if g == EASY else 1) + 1)


def forget_s(d, s, r):
    return min(W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r)), s)


def short_s(s, g):
    inc = math.exp(W[17] * (g - 3 + W[18])) * s ** -W[19]
    return s * (max(inc, 1) if g >= 2 else inc)


def review(mem, days, g):
    if mem is None:
        return (max(W[g - 1], 0.01), D0(g))
    s, d = mem
    if days < 1:
        s2 = short_s(s, g)
    else:
        r = R(days, s)
        s2 = forget_s(d, s, r) if g == AGAIN else recall_s(d, s, r, g)
    return (max(s2, 0.01), next_d(d, g))


def history(grades):
    """Review on the due date each time ("Again" -> back 10 minutes later)."""
    mem, out, wait = None, [], 0.0
    for g in grades:
        mem = review(mem, wait, g)
        wait = 10 / 1440 if g == AGAIN else interval(mem[0])
        out.append((g, round(mem[0], 2), round(mem[1], 2), wait if g != AGAIN else "10 min"))
    return out


if __name__ == "__main__":
    assert abs(R(5, 5) - 0.9) < 1e-9          # by construction, recall is 90% after S days
    assert interval(10) == 10
    for name, grades in [("always got it", [GOOD] * 6),
                         ("missed first, then got it", [AGAIN, GOOD, GOOD, GOOD, GOOD]),
                         ("lapse after a month", [GOOD, GOOD, GOOD, AGAIN, GOOD, GOOD])]:
        print(name)
        for row in history(grades):
            print("   grade %d  S=%-7s D=%-5s next=%s" % row)
    h = history([GOOD] * 6)
    assert all(h[i][1] < h[i + 1][1] for i in range(5)), "stability should grow with each success"
    h = history([GOOD, GOOD, GOOD, AGAIN])
    assert h[3][1] < h[2][1], "a lapse should lower stability"
    print("ok")
