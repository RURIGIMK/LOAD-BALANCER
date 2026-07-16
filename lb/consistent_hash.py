import bisect  # binary search helpers for locating slots on the sorted ring
import re  # extract numeric IDs out of server hostnames like "Server3" or "S5"

class ConsistentHash:
    def __init__(self, M=512, K=9, H=None, Phi=None, probing='quadratic'):
        self.M = M  # total number of slots in the circular hash map (spec: 512)
        self.K = K  # virtual nodes per physical server (spec: log2(512) = 9)
        # Default hash functions per assignment spec:
        # H(i) = i^2 + 2i + 17   (request -> slot)
        # Phi(i,j) = i^2 + j^2 + 2j + 25   (virtual server -> slot)
        self.H = H if H else lambda i: (i**2 + 2 * i + 17) % M  # request-ID hash, falls back to spec formula if none given
        self.Phi = Phi if Phi else lambda i, j: (i**2 + j**2 + 2 * j + 25) % M  # virtual-server hash, falls back to spec formula
        self.probing = probing  # collision resolution strategy: 'linear' or 'quadratic'

        self.ring = {}  # maps slot number -> server_id occupying that slot
        self.sorted_slots = []  # kept sorted so we can bisect to find the next clockwise slot
        self.servers = set()  # set of currently active server_ids, used to avoid duplicate adds

    def _server_to_int(self, server_id):
        """Convert 'Server1' or 'S5' to a stable integer."""
        nums = re.findall(r'\d+', server_id)  # pull out digit runs from the hostname
        if nums:
            return int(nums[-1])  # e.g., Server1 -> 1, S5 -> 5
        return abs(hash(server_id)) % (10**9)  # fallback for hostnames with no digits

    def add_server(self, server_id):
        if server_id in self.servers:
            return  # already present, nothing to do
        self.servers.add(server_id)  # mark this server as active
        server_int = self._server_to_int(server_id)  # numeric ID fed into Phi
        for j in range(self.K):  # place K virtual nodes for this server
            base_slot = self.Phi(server_int, j)  # ideal slot from the hash function
            slot = base_slot  # slot we'll actually try to occupy
            probe = 1  # probe counter for collision resolution
            while slot in self.ring:  # keep probing while the slot is taken
                if self.probing == 'quadratic':
                    slot = (base_slot + probe * probe) % self.M  # quadratic probing step
                else:
                    slot = (base_slot + probe) % self.M  # linear probing step
                probe += 1  # advance probe sequence
            self.ring[slot] = server_id  # occupy the free slot with this server
            bisect.insort(self.sorted_slots, slot)  # keep sorted_slots sorted for bisecting later

    def remove_server(self, server_id):
        if server_id not in self.servers:
            return  # nothing to remove
        self.servers.remove(server_id)  # drop from active set
        slots_to_remove = [s for s, sid in self.ring.items() if sid == server_id]  # find all its virtual node slots
        for slot in slots_to_remove:
            del self.ring[slot]  # free the slot
            self.sorted_slots.remove(slot)  # keep sorted_slots in sync

    def get_server(self, request_id):
        if not self.servers:
            return None  # no servers to route to
        slot = self.H(request_id)  # map the request onto the ring
        idx = bisect.bisect_left(self.sorted_slots, slot)  # find first occupied slot >= request's slot
        if idx == len(self.sorted_slots):
            idx = 0  # wrap around the circle back to the first slot
        return self.ring[self.sorted_slots[idx]]  # the server owning that clockwise-nearest slot
