"""Deterministic random number generation.

Every save stores explicit RNG stream states as plain integers so that
(seed + same inputs) always replays to the identical outcome, across
Python versions and platforms. We implement xoroshiro128** ourselves
rather than relying on random.Random so the state is JSON-serializable
and the algorithm is frozen.

Each subsystem (economy, credit, fraud, ...) gets its own named stream so
that adding a draw in one subsystem never perturbs the sequence seen by
another.
"""

import math

MASK64 = (1 << 64) - 1


def _splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK64
    return x, (z ^ (z >> 31)) & MASK64


def seed_stream(master_seed, name):
    """Derive an independent [s0, s1] stream state from a master seed and a name."""
    x = master_seed & MASK64
    for ch in name.encode("utf-8"):
        x, _ = _splitmix64(x ^ ch)
    x, s0 = _splitmix64(x)
    x, s1 = _splitmix64(x)
    if s0 == 0 and s1 == 0:
        s1 = 0x9E3779B97F4A7C15
    return [s0, s1]


def _rotl(x, k):
    return ((x << k) | (x >> (64 - k))) & MASK64


class Rng:
    """xoroshiro128** wrapped around a mutable [s0, s1] list.

    The list is owned by the save-state dict; mutating it in place means
    stream positions persist through save/load automatically.
    """

    def __init__(self, state_list):
        self.s = state_list

    def u64(self):
        s0, s1 = self.s
        result = (_rotl((s0 * 5) & MASK64, 7) * 9) & MASK64
        s1 ^= s0
        self.s[0] = _rotl(s0, 24) ^ s1 ^ ((s1 << 16) & MASK64)
        self.s[1] = _rotl(s1, 37)
        return result

    def random(self):
        """Uniform float in [0, 1)."""
        return (self.u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, a, b):
        return a + (b - a) * self.random()

    def randint(self, a, b):
        """Inclusive integer range."""
        return a + self.u64() % (b - a + 1)

    def normal(self, mu=0.0, sigma=1.0):
        # Box-Muller without spare caching (caching would make state
        # incomplete across save/load).
        u1 = self.random()
        u2 = self.random()
        while u1 <= 1e-12:
            u1 = self.random()
        z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return mu + sigma * z

    def lognormal(self, mu=0.0, sigma=1.0):
        return math.exp(self.normal(mu, sigma))

    def expovariate(self, lam):
        u = self.random()
        while u <= 1e-12:
            u = self.random()
        return -math.log(u) / lam

    def poisson(self, lam):
        if lam <= 0:
            return 0
        if lam < 30:
            l = math.exp(-lam)
            k = 0
            p = 1.0
            while True:
                p *= self.random()
                if p <= l:
                    return k
                k += 1
        # Normal approximation for large lambda
        return max(0, int(round(self.normal(lam, math.sqrt(lam)))))

    def choice(self, seq):
        return seq[self.u64() % len(seq)]

    def weighted_choice(self, pairs):
        """pairs: list of (item, weight). Deterministic order matters."""
        total = sum(w for _, w in pairs)
        r = self.random() * total
        acc = 0.0
        for item, w in pairs:
            acc += w
            if r < acc:
                return item
        return pairs[-1][0]

    def chance(self, p):
        return self.random() < p

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = self.u64() % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]


def make_streams(master_seed, names):
    return {name: seed_stream(master_seed, name) for name in names}
