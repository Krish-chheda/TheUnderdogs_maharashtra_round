import unittest
from types import SimpleNamespace

from app.services.allocation import calculate_quotas, randomized_order


class AllocationPolicyTests(unittest.TestCase):
    def test_example_batch_quotas(self):
        quotas = calculate_quotas(
            {0: 8000, 1: 12000, 2: 10000, 3: 15000, 4: 5000},
            500,
            [0.30, 0.25, 0.20, 0.15, 0.10],
        )
        self.assertEqual(quotas, {0: 150, 1: 125, 2: 100, 3: 75, 4: 50})

    def test_insufficient_batch_redistributes_without_oversell(self):
        quotas = calculate_quotas({0: 1, 1: 100, 2: 100}, 50, [0.50, 0.30, 0.20])
        self.assertEqual(sum(quotas.values()), 50)
        self.assertEqual(quotas[0], 1)
        self.assertLessEqual(quotas[1], 100)
        self.assertLessEqual(quotas[2], 100)

    def test_randomization_is_reproducible(self):
        entries = [SimpleNamespace(id=str(index)) for index in range(100)]
        first = [entry.id for entry in randomized_order(entries, b"seed")]
        second = [entry.id for entry in randomized_order(entries, b"seed")]
        self.assertEqual(first, second)
        self.assertEqual(set(first), {str(index) for index in range(100)})

    def test_fifty_thousand_entries_never_exceed_capacity(self):
        counts = {index: 10000 for index in range(5)}
        quotas = calculate_quotas(counts, 500, [0.30, 0.25, 0.20, 0.15, 0.10])
        self.assertEqual(sum(quotas.values()), 500)
        self.assertTrue(all(quotas[index] <= counts[index] for index in counts))


if __name__ == "__main__":
    unittest.main()
