class Tracker:
    def __init__(self):
        self.peers = {}  # peer_id: (ip, port, blocks)

    def register_peer(self, peer_info):
        # Adiciona peer e retorna lista de peers disponíveis

    def get_random_peers(self, requesting_peer_id, max_peers=5):
        # Retorna subconjunto aleatório de peers (exceto o solicitante)
