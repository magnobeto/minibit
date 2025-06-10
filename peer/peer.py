class Peer:
    def __init__(self, peer_id, tracker_address):
        self.peer_id = peer_id
        self.block_manager = BlockManager()
        self.unchoke_manager = UnchokeManager()
        self.peers = set()

    def join_network(self):
        # Registra no tracker e recebe blocos iniciais

    def run(self):
        # Loop principal de operação (comunicação, troca de blocos, unchoke)

    def shutdown(self):
        # Reconstrói o arquivo completo e encerra
