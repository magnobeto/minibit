import random
import time
import logging
from typing import Dict, Set, List, Tuple, Optional
from dataclasses import dataclass
from threading import Lock

@dataclass
class PeerStatistics:
    """Armazena estatísticas de um peer para decisões de choke/unchoke."""
    peer_id: str
    download_rate: float = 0.0  # Bytes por segundo
    last_received_time: float = 0.0
    blocks_received: int = 0
    total_bytes_received: int = 0
    upload_allowed: bool = False
    is_interested: bool = False
    last_update_time: float = 0.0

class UnchokeManager:
    """
    Gerencia a estratégia de choke/unchoke usando o algoritmo tit-for-tat
    e seleção periódica de um peer otimista.
    """
    
    # Parâmetros do algoritmo
    MAX_FIXED_UNCHOKED = 3  # Número máximo de peers não-choked fixos
    OPTIMISTIC_INTERVAL = 30  # Intervalo para alterar peer otimista (segundos)
    EVALUATION_INTERVAL = 10  # Intervalo para reavaliação de peers (segundos)
    
    def __init__(self):
        """
        Inicializa o gerenciador de choke/unchoke.
        """
        # Conjunto de IDs de peers desbloqueados por taxa de download
        self.fixed_peers: Set[str] = set()
        # ID do peer otimisticamente desbloqueado
        self.optimistic_peer: Optional[str] = None
        
        # Estatísticas de todos os peers conhecidos
        self.peer_stats: Dict[str, PeerStatistics] = {}
        
        # Controle de tempo
        self.last_optimistic_change: float = 0
        self.last_evaluation_time: float = 0
        
        # Bloqueio para acessar os dados
        self.lock = Lock()
        
        # Configuração de logger
        self.logger = logging.getLogger("UnchokeManager")
    
    def register_peer(self, peer_id: str) -> None:
        """
        Registra um novo peer no sistema.
        
        Args:
            peer_id: ID único do peer
        """
        with self.lock:
            if peer_id not in self.peer_stats:
                self.peer_stats[peer_id] = PeerStatistics(
                    peer_id=peer_id,
                    last_update_time=time.time()
                )
                self.logger.info(f"Novo peer registrado: {peer_id}")
    
    def unregister_peer(self, peer_id: str) -> None:
        """
        Remove um peer do sistema.
        
        Args:
            peer_id: ID do peer a ser removido
        """
        with self.lock:
            if peer_id in self.peer_stats:
                del self.peer_stats[peer_id]
                
            if peer_id in self.fixed_peers:
                self.fixed_peers.remove(peer_id)
                
            if self.optimistic_peer == peer_id:
                self.optimistic_peer = None
                self.last_optimistic_change = 0  # Forçar nova seleção
    
    def record_download(self, peer_id: str, bytes_received: int) -> None:
        """
        Registra estatísticas de download de um peer.
        
        Args:
            peer_id: ID do peer
            bytes_received: Quantidade de bytes recebidos
        """
        with self.lock:
            current_time = time.time()
            
            if peer_id not in self.peer_stats:
                self.register_peer(peer_id)
            
            stats = self.peer_stats[peer_id]
            stats.blocks_received += 1
            stats.total_bytes_received += bytes_received
            
            # Calcula a taxa de download
            elapsed = current_time - stats.last_update_time
            if elapsed > 0:
                # Média ponderada para suavizar as flutuações
                new_rate = bytes_received / elapsed
                if stats.download_rate > 0:
                    stats.download_rate = 0.7 * stats.download_rate + 0.3 * new_rate
                else:
                    stats.download_rate = new_rate
            
            stats.last_received_time = current_time
            stats.last_update_time = current_time
    
    def set_peer_interested(self, peer_id: str, interested: bool) -> None:
        """
        Define o status 'interested' de um peer.
        
        Args:
            peer_id: ID do peer
            interested: True se o peer está interessado, False caso contrário
        """
        with self.lock:
            if peer_id not in self.peer_stats:
                self.register_peer(peer_id)
                
            self.peer_stats[peer_id].is_interested = interested
    
    def evaluate_peers(self, force: bool = False) -> bool:
        """
        Avalia todos os peers e atualiza os status de choke/unchoke.
        
        Args:
            force: Se True, força uma reavaliação mesmo que não seja o momento
            
        Returns:
            True se os peers foram reavaliados, False caso contrário
        """
        current_time = time.time()
        
        # Verificar se é hora de reavaliar
        if not force and (current_time - self.last_evaluation_time < self.EVALUATION_INTERVAL):
            return False
        
        with self.lock:
            self.last_evaluation_time = current_time
            
            # Filtra apenas os peers interessados
            interested_peers = [
                (peer_id, stats) for peer_id, stats in self.peer_stats.items()
                if stats.is_interested
            ]
            
            # Ordena por taxa de download (maior para menor)
            sorted_peers = sorted(
                interested_peers, 
                key=lambda x: x[1].download_rate, 
                reverse=True
            )
            
            # Seleciona os melhores peers para fixed_peers
            new_fixed_peers = set()
            for i, (peer_id, _) in enumerate(sorted_peers):
                if i < self.MAX_FIXED_UNCHOKED:
                    new_fixed_peers.add(peer_id)
                else:
                    break
                    
            # Verifica mudança em peers fixos
            if new_fixed_peers != self.fixed_peers:
                self.logger.info(f"Atualizando peers fixos: {new_fixed_peers}")
                
                # Para os peers que serão choked
                for peer_id in self.fixed_peers - new_fixed_peers:
                    if peer_id in self.peer_stats:
                        self.peer_stats[peer_id].upload_allowed = False
                
                # Para os peers que serão unchoked
                for peer_id in new_fixed_peers - self.fixed_peers:
                    if peer_id in self.peer_stats:
                        self.peer_stats[peer_id].upload_allowed = True
                
                self.fixed_peers = new_fixed_peers
            
            # Verifica se é hora de atualizar o peer otimista
            self._update_optimistic_peer(current_time)
            
            return True
    
    def get_unchoked_peers(self) -> List[str]:
        """
        Retorna a lista de peers que estão atualmente desbloqueados.
        
        Returns:
            Lista de IDs de peers desbloqueados
        """
        with self.lock:
            unchoked = list(self.fixed_peers)
            if self.optimistic_peer and self.optimistic_peer not in self.fixed_peers:
                unchoked.append(self.optimistic_peer)
            return unchoked
    
    def is_unchoked(self, peer_id: str) -> bool:
        """
        Verifica se um peer específico está desbloqueado.
        
        Args:
            peer_id: ID do peer
            
        Returns:
            True se o peer está desbloqueado, False caso contrário
        """
        with self.lock:
            return peer_id in self.fixed_peers or peer_id == self.optimistic_peer
    
    def get_peer_statistics(self) -> List[Tuple[str, float, bool]]:
        """
        Retorna estatísticas de todos os peers para monitoramento.
        
        Returns:
            Lista de tuplas (peer_id, taxa_download, desbloqueado)
        """
        with self.lock:
            result = []
            for peer_id, stats in self.peer_stats.items():
                is_unchoked = peer_id in self.fixed_peers or peer_id == self.optimistic_peer
                result.append((peer_id, stats.download_rate, is_unchoked))
            return result
    
    def _update_optimistic_peer(self, current_time: float) -> None:
        """
        Atualiza o peer otimista se for o momento.
        
        Args:
            current_time: Tempo atual em segundos (time.time())
        """
        # Verificar se é hora de atualizar o peer otimista
        if current_time - self.last_optimistic_change >= self.OPTIMISTIC_INTERVAL:
            # Encontra peers interessados que não estão na lista fixed
            potential_peers = [
                peer_id for peer_id, stats in self.peer_stats.items()
                if stats.is_interested and peer_id not in self.fixed_peers
            ]
            
            if potential_peers:
                # Escolhe aleatoriamente um peer otimista
                old_peer = self.optimistic_peer
                self.optimistic_peer = random.choice(potential_peers)
                
                # Atualiza status
                if old_peer and old_peer not in self.fixed_peers and old_peer in self.peer_stats:
                    self.peer_stats[old_peer].upload_allowed = False
                
                if self.optimistic_peer in self.peer_stats:
                    self.peer_stats[self.optimistic_peer].upload_allowed = True
                    
                self.logger.info(f"Novo peer otimista: {self.optimistic_peer}")
            else:
                self.optimistic_peer = None
                
            self.last_optimistic_change = current_time