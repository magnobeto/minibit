import random
from typing import Dict, List, Tuple, Set, Optional

class Tracker:
    """
    Tracker central para o sistema MiniBit.
    
    Responsável por:
    - Registrar e gerenciar informações dos peers conectados
    - Fornecer lista de peers disponíveis para novos participantes
    - Retornar subconjuntos aleatórios de peers quando solicitado
    
    A estrutura principal armazena para cada peer:
    - peer_id: identificador único do peer
    - ip: endereço IP do peer
    - port: porta de comunicação
    - blocks: conjunto de blocos que o peer possui
    """
    
    def __init__(self):
        self.peers: Dict[str, Tuple[str, int, Set[int]]] = {}

    def register_peer(self, peer_info: Tuple[str, str, int, Set[int]]) -> List[Tuple[str, str, int, Set[int]]]:
        """
        Registra um novo peer ou atualiza dados de um peer existente.
        Retorna uma lista de peers disponíveis para conexão.
        """
        peer_id, ip, port, blocks = peer_info
        
        self.peers[peer_id] = (ip, port, blocks)
        
        available_peers = []
        for pid, (p_ip, p_port, p_blocks) in self.peers.items():
            if pid != peer_id:
                available_peers.append((pid, p_ip, p_port, p_blocks))
        
        if len(self.peers) <= 5:
            return available_peers
        else:
            return self.get_random_peers(peer_id)
    
    def get_random_peers(self, requesting_peer_id: str, max_peers: int = 5) -> List[Tuple[str, str, int, Set[int]]]:
        """
        Retorna um subconjunto aleatório de peers disponíveis.
        Exclui o peer solicitante da lista retornada.
        """
        available_peer_ids = [pid for pid in self.peers.keys() if pid != requesting_peer_id]
        
        if len(available_peer_ids) <= max_peers:
            selected_peer_ids = available_peer_ids
        else:
            selected_peer_ids = random.sample(available_peer_ids, max_peers)
        
        selected_peers = []
        for pid in selected_peer_ids:
            ip, port, blocks = self.peers[pid]
            selected_peers.append((pid, ip, port, blocks))
        
        return selected_peers
    
    def update_peer_blocks(self, peer_id: str, blocks: Set[int]) -> Optional[bool]:
        """
        Atualiza o conjunto de blocos que um peer possui.
        """
        if peer_id in self.peers:
            ip, port, _ = self.peers[peer_id]
            self.peers[peer_id] = (ip, port, blocks)
            return True
        return None
    
    def remove_peer(self, peer_id: str) -> Optional[bool]:
        """
        Remove um peer do tracker quando ele se desconecta.
        """
        if peer_id in self.peers:
            del self.peers[peer_id]
            return True
        return None