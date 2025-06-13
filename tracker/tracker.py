import random
from typing import Dict, List, Tuple, Set, Optional

class Tracker:
    def __init__(self):
        # Dicionário que armazena informações dos peers: peer_id -> (ip, port, blocks)
        # Onde 'blocks' é um conjunto dos blocos que o peer possui
        self.peers: Dict[str, Tuple[str, int, Set[int]]] = {}

    def register_peer(self, peer_info: Tuple[str, str, int, Set[int]]) -> List[Tuple[str, str, int, Set[int]]]:
        """
        Adiciona um novo peer ao tracker e retorna lista de peers disponíveis
        
        Args:
            peer_info: Tupla contendo (peer_id, ip, port, blocks)
            
        Returns:
            Lista de peers disponíveis (peer_id, ip, port, blocks)
        """
        peer_id, ip, port, blocks = peer_info
        
        # Registra ou atualiza as informações do peer
        self.peers[peer_id] = (ip, port, blocks)
        
        # Prepara a lista de peers para retornar
        # Excluindo o próprio peer da resposta
        available_peers = []
        for pid, (p_ip, p_port, p_blocks) in self.peers.items():
            if pid != peer_id:  # Não incluir o próprio peer solicitante
                available_peers.append((pid, p_ip, p_port, p_blocks))
        
        # Se houver mais de 5 peers, retorna um subconjunto aleatório
        if len(self.peers) <= 5:
            return available_peers
        else:
            return self.get_random_peers(peer_id)
    
    def get_random_peers(self, requesting_peer_id: str, max_peers: int = 5) -> List[Tuple[str, str, int, Set[int]]]:
        """
        Retorna um subconjunto aleatório de peers disponíveis, excluindo o solicitante
        
        Args:
            requesting_peer_id: ID do peer que está fazendo a solicitação
            max_peers: Número máximo de peers a retornar
            
        Returns:
            Lista de peers selecionados (peer_id, ip, port, blocks)
        """
        # Obtém a lista de peers, excluindo o solicitante
        available_peer_ids = [pid for pid in self.peers.keys() if pid != requesting_peer_id]
        
        # Se houver menos peers que o máximo solicitado, retorna todos disponíveis
        if len(available_peer_ids) <= max_peers:
            selected_peer_ids = available_peer_ids
        else:
            # Seleciona aleatoriamente um subconjunto de peers
            selected_peer_ids = random.sample(available_peer_ids, max_peers)
        
        # Constrói a lista de retorno com as informações completas dos peers selecionados
        selected_peers = []
        for pid in selected_peer_ids:
            ip, port, blocks = self.peers[pid]
            selected_peers.append((pid, ip, port, blocks))
        
        return selected_peers
    
    def update_peer_blocks(self, peer_id: str, blocks: Set[int]) -> Optional[bool]:
        """
        Atualiza o conjunto de blocos que um peer possui
        
        Args:
            peer_id: ID do peer
            blocks: Novo conjunto de blocos
            
        Returns:
            True se a atualização foi bem-sucedida, None se o peer não existe
        """
        if peer_id in self.peers:
            ip, port, _ = self.peers[peer_id]
            self.peers[peer_id] = (ip, port, blocks)
            return True
        return None
    
    def remove_peer(self, peer_id: str) -> Optional[bool]:
        """
        Remove um peer do tracker
        
        Args:
            peer_id: ID do peer a ser removido
            
        Returns:
            True se a remoção foi bem-sucedida, None se o peer não existe
        """
        if peer_id in self.peers:
            del self.peers[peer_id]
            return True
        return None