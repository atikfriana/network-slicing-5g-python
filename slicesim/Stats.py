class Stats:
    def __init__(self, env, base_stations, clients, area: tuple):
        """
        Initialize statistics collector for the simulation.
        """
        self.env = env
        self.base_stations = base_stations
        self.clients = clients
        self.area = area
        #self.graph = graph

        # Stats
        self.total_connected_users_ratio = []
        self.total_used_bw = []
        self.avg_slice_load_ratio = []
        self.avg_slice_client_count = []
        self.coverage_ratio = []
        self.connect_attempt = []
        self.block_count = []
        self.handover_count = []
    
    def get_stats(self) -> tuple:
        """
        Return all collected statistics as a tuple.
        """
        return (
            self.total_connected_users_ratio,
            self.total_used_bw,
            self.avg_slice_load_ratio,
            self.avg_slice_client_count,
            self.coverage_ratio,
            self.block_count,
            self.handover_count,
        )

    def collect(self):
        """
        Collect statistics at each simulation step.
        """
        yield self.env.timeout(0.25)
        self.connect_attempt.append(0)
        self.block_count.append(0)
        self.handover_count.append(0)
        while True:
            self.block_count[-1] /= self.connect_attempt[-1] if self.connect_attempt[-1] != 0 else 1
            self.handover_count[-1] /= self.connect_attempt[-1] if self.connect_attempt[-1] != 0 else 1

            self.total_connected_users_ratio.append(self.get_total_connected_users_ratio())
            self.total_used_bw.append(self.get_total_used_bw())
            self.avg_slice_load_ratio.append(self.get_avg_slice_load_ratio())
            self.avg_slice_client_count.append(self.get_avg_slice_client_count())
            self.coverage_ratio.append(self.get_coverage_ratio())

            self.connect_attempt.append(0)
            self.block_count.append(0)
            self.handover_count.append(0)
            yield self.env.timeout(1)

    def get_total_connected_users_ratio(self) -> float:
        """
        Calculate the ratio of connected users to total users in coverage.
        """
        t, cc = 0, 0
        for c in self.clients:
            if self.is_client_in_coverage(c):
                t += c.connected
                cc += 1
        # for bs in self.base_stations:
        #     for sl in bs.slices:
        #         t += sl.connected_users
        return t/cc if cc != 0 else 0

    def get_total_used_bw(self) -> float:
        """
        Calculate the total used bandwidth across all slices and base stations.
        """
        t = 0
        for bs in self.base_stations:
            for sl in bs.slices:
                t += sl.capacity.capacity - sl.capacity.level
        return t

    def get_avg_slice_load_ratio(self) -> float:
        """
        Calculate the average load ratio across all slices.
        """
        t, c = 0, 0
        for bs in self.base_stations:
            for sl in bs.slices:
                c += sl.capacity.capacity
                t += sl.capacity.capacity - sl.capacity.level
                #c += 1
                #t += (sl.capacity.capacity - sl.capacity.level) / sl.capacity.capacity
        return t/c if c !=0 else 0

    def get_avg_slice_client_count(self) -> float:
        """
        Calculate the average number of clients per slice.
        """
        t, c = 0, 0
        for bs in self.base_stations:
            for sl in bs.slices:
                c += 1
                t += sl.connected_users
        return t/c if c !=0 else 0
    
    def get_coverage_ratio(self) -> float:
        """
        Calculate the ratio of clients in coverage and connected to a base station.
        """
        t, cc = 0, 0
        for c in self.clients:
            if self.is_client_in_coverage(c):
                cc += 1
                if c.base_station is not None and c.base_station.coverage.is_in_coverage(c.x, c.y):
                    t += 1
        return t/cc if cc !=0 else 0

    def incr_connect_attempt(self, client) -> None:
        if self.is_client_in_coverage(client):
            self.connect_attempt[-1] += 1

    def incr_block_count(self, client) -> None:
        if self.is_client_in_coverage(client):
            self.block_count[-1] += 1

    def incr_handover_count(self, client) -> None:
        if self.is_client_in_coverage(client):
            self.handover_count[-1] += 1

    def is_client_in_coverage(self, client) -> bool:
        xs, ys = self.area
        return True if xs[0] <= client.x <= xs[1] and ys[0] <= client.y <= ys[1] else False
        