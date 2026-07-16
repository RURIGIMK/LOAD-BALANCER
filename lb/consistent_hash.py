import bisect
import re

class ConsistentHash:
    def __init__(self, M=512, K=9, H=None, Phi=None):
        self.M = M            # ring size (number of slots)
        self.K = K            # virtual nodes per server
        self.H = H if H else lambda i: (5 * i + 2) % M          # request hash function
        self.Phi = Phi if Phi else lambda i, j: (i + 3 * j + 25) % M  # server virtual-node hash function

        self.ring = {}          # slot -> server_id
        self.sorted_slots = []  # sorted list of occupied slots for binary search
        self.servers = set()    # set of currently registered server ids

    def _server_to_int(self, server_id):
        """Convert 'Server1' or 'S5' to a stable integer."""
        nums = re.findall(r'\d+', server_id)
        if nums:
            return int(nums[-1])  # e.g., Server1 -> 1, S5 -> 5
        return abs(hash(server_id)) % (10**9)

    def add_server(self, server_id):
        # Place K virtual nodes for this server on the ring, resolving collisions linearly
        if server_id in self.servers:
            return
        self.servers.add(server_id)
        server_int = self._server_to_int(server_id)
        for j in range(self.K):
            slot = self.Phi(server_int, j)   # <-- now passing int
            while slot in self.ring:
                slot = (slot + 1) % self.M   # linear probe on collision
            self.ring[slot] = server_id
            bisect.insort(self.sorted_slots, slot)  # keep sorted for binary search lookup

    def remove_server(self, server_id):
        # Remove all virtual node slots belonging to this server
        if server_id not in self.servers:
            return
        self.servers.remove(server_id)
        slots_to_remove = [s for s, sid in self.ring.items() if sid == server_id]
        for slot in slots_to_remove:
            del self.ring[slot]
            self.sorted_slots.remove(slot)

    def get_server(self, request_id):
        # Hash request onto ring, then find the next server slot clockwise (wrap to first if past end)
        if not self.servers:
            return None
        slot = self.H(request_id)
        idx = bisect.bisect_left(self.sorted_slots, slot)
        if idx == len(self.sorted_slots):
            idx = 0  # wrap around the ring
        return self.ring[self.sorted_slots[idx]]