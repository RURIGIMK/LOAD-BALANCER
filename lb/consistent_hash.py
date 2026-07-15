import bisect
import re

class ConsistentHash:
    def __init__(self, M=512, K=9, H=None, Phi=None):
        self.M = M
        self.K = K
        self.H = H if H else lambda i: (5 * i + 2) % M
        self.Phi = Phi if Phi else lambda i, j: (i + 3 * j + 25) % M

        self.ring = {}
        self.sorted_slots = []
        self.servers = set()

    def _server_to_int(self, server_id):
        """Convert 'Server1' or 'S5' to a stable integer."""
        nums = re.findall(r'\d+', server_id)
        if nums:
            return int(nums[-1])  # e.g., Server1 -> 1, S5 -> 5
        return abs(hash(server_id)) % (10**9)

    def add_server(self, server_id):
        if server_id in self.servers:
            return
        self.servers.add(server_id)
        server_int = self._server_to_int(server_id)
        for j in range(self.K):
            slot = self.Phi(server_int, j)   # <-- now passing int
            while slot in self.ring:
                slot = (slot + 1) % self.M
            self.ring[slot] = server_id
            bisect.insort(self.sorted_slots, slot)

    def remove_server(self, server_id):
        if server_id not in self.servers:
            return
        self.servers.remove(server_id)
        slots_to_remove = [s for s, sid in self.ring.items() if sid == server_id]
        for slot in slots_to_remove:
            del self.ring[slot]
            self.sorted_slots.remove(slot)

    def get_server(self, request_id):
        if not self.servers:
            return None
        slot = self.H(request_id)
        idx = bisect.bisect_left(self.sorted_slots, slot)
        if idx == len(self.sorted_slots):
            idx = 0
        return self.ring[self.sorted_slots[idx]]