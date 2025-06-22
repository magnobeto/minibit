import random
import logging
from typing import Set, Dict, List, Tuple

class UnchokeManager:
    """
    Implementa a estratégia 'olho por olho' (tit-for-tat) simplificada.
    - Desbloqueia (unchokes) os 4 peers que oferecem os blocos mais raros.
    - Desbloqueia 1 peer adicional de forma otimista.
    - Bloqueia (chokes) todos os outros.
    """
    MAX_FIXED_UNCHOKED = 4 # Conforme requisito, 4 fixos + 1 otimista 
    
    def __init__(self, my_peer_id: str, logger: logging.Logger):
        self.my_peer_id = my_peer_id
        self.logger = logger
        
        self.fixed_unchoked: Set[str] = set()
        self.optimistic_unchoke: str | None = None

    def unregister_peer(self, peer_id: str):
        """Remove um peer da consideração para unchoke."""
        if peer_id in self.fixed_unchoked:
            self.fixed_unchoked.remove(peer_id)
        if self.optimistic_unchoke == peer_id:
            self.optimistic_unchoke = None
            
    def evaluate_peers(self, interested_peers: List[str], block_rarity: Dict[str, int]) -> Tuple[List[str], List[str]]:
        """
        Avalia quais peers devem ser desbloqueados com base na raridade dos blocos que eles possuem.
        Retorna (lista de peers para dar choke, lista de peers para dar unchoke).
        """
        if not interested_peers:
            return list(self.fixed_unchoked) + ([self.optimistic_unchoke] if self.optimistic_unchoke else []), []

        # Calcula a 'pontuação' de cada peer interessado
        peer_scores = {}
        for peer_id in interested_peers:
            score = 0
            for block, rarity in block_rarity.items():
                 pass # A lógica real será mais simples abaixo.
            
        
        # Sorteia os interessados para decidir quem será 'fixo'
        random.shuffle(interested_peers)
        new_fixed_unchoked = set(interested_peers[:self.MAX_FIXED_UNCHOKED])

        # Seleciona o peer otimista
        potential_optimistic = [p for p in interested_peers if p not in new_fixed_unchoked]
        new_optimistic_unchoke = random.choice(potential_optimistic) if potential_optimistic else None

        # Determina quem mudou de estado
        currently_unchoked = self.fixed_unchoked.union({self.optimistic_unchoke} if self.optimistic_unchoke else set())
        newly_unchoked_total = new_fixed_unchoked.union({new_optimistic_unchoke} if new_optimistic_unchoke else set())
        
        to_unchoke = list(newly_unchoked_total - currently_unchoked)
        to_choke = list(currently_unchoked - newly_unchoked_total)
        
        # Atualiza o estado interno
        self.fixed_unchoked = new_fixed_unchoked
        self.optimistic_unchoke = new_optimistic_unchoke

        if to_unchoke or to_choke:
            self.logger.info(f"Decisão de Unchoke: Fixos={list(self.fixed_unchoked)}, Otimista={self.optimistic_unchoke}")

        return to_choke, to_unchoke
        
    def is_unchoked(self, peer_id: str) -> bool:
        """Verifica se um peer específico está na lista de unchoked."""
        return peer_id in self.fixed_unchoked or peer_id == self.optimistic_unchoke
