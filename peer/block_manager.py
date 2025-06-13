import random
from typing import Dict, Set, List, Optional

class BlockManager:
    """
    Gerencia os blocos de um arquivo distribuído na rede P2P.
    Responsável por rastrear blocos disponíveis e ausentes, bem como 
    implementar a estratégia "rarest first" para seleção de blocos.
    """
    
    def __init__(self):
        """Inicializa o gerenciador de blocos."""
        self.blocks: Dict[str, bytes] = {}  # Mapeamento de ID do bloco para dados
        self.total_blocks: Set[str] = set()  # Todos os IDs de blocos no sistema
        self.rarity_info: Dict[str, int] = {}  # Rastreamento de raridade: block_id -> contagem
    
    def load_initial_blocks(self, total_blocks: List[str], initial_count: int = 0):
        """
        Inicializa o gerenciador com um conjunto de blocos inicial.
        
        Args:
            total_blocks: Lista de todos os IDs de blocos no sistema
            initial_count: Número de blocos para inicializar aleatoriamente
        """
        self.total_blocks = set(total_blocks)
        self.rarity_info = {block_id: 0 for block_id in total_blocks}
        
        # Se initial_count for maior que zero, seleciona blocos aleatoriamente
        if initial_count > 0:
            initial_subset = random.sample(total_blocks, 
                                          min(initial_count, len(total_blocks)))
            for block_id in initial_subset:
                # Placeholder para dados reais - em uma implementação real, 
                # carregaria dados do arquivo
                self.blocks[block_id] = f"Data for block {block_id}".encode()
    
    def has_block(self, block_id: str) -> bool:
        """
        Verifica se um bloco específico está disponível localmente.
        
        Args:
            block_id: ID do bloco a verificar
            
        Returns:
            True se o bloco estiver disponível, False caso contrário
        """
        return block_id in self.blocks
    
    def get_blocks(self) -> Set[str]:
        """
        Retorna o conjunto de IDs de blocos disponíveis localmente.
        
        Returns:
            Conjunto de IDs de blocos
        """
        return set(self.blocks.keys())
    
    def get_missing_blocks(self) -> Set[str]:
        """
        Retorna o conjunto de IDs de blocos que ainda não estão disponíveis.
        
        Returns:
            Conjunto de IDs de blocos ausentes
        """
        return self.total_blocks - set(self.blocks.keys())
    
    def add_block(self, block_id: str, data: bytes) -> bool:
        """
        Adiciona um novo bloco ao gerenciador.
        
        Args:
            block_id: ID do bloco
            data: Dados do bloco
            
        Returns:
            True se o bloco foi adicionado com sucesso, False caso contrário
        """
        if block_id in self.blocks:
            return False
        
        if block_id not in self.total_blocks:
            return False
            
        self.blocks[block_id] = data
        return True
    
    def get_block_data(self, block_id: str) -> Optional[bytes]:
        """
        Recupera os dados de um bloco específico.
        
        Args:
            block_id: ID do bloco
            
        Returns:
            Dados do bloco ou None se o bloco não estiver disponível
        """
        return self.blocks.get(block_id)
    
    def is_complete(self) -> bool:
        """
        Verifica se todos os blocos estão disponíveis.
        
        Returns:
            True se todos os blocos estiverem disponíveis, False caso contrário
        """
        return len(self.blocks) == len(self.total_blocks)
    
    def update_rarity_info(self, peer_id: str, blocks: Set[str]):
        """
        Atualiza informações de raridade com base nos blocos disponíveis em um peer.
        
        Args:
            peer_id: ID do peer
            blocks: Conjunto de blocos disponíveis no peer
        """
        # Esta implementação seria expandida em uma versão real para rastrear 
        # blocos por peer e calcular raridade
        for block_id in blocks:
            if block_id in self.rarity_info:
                self.rarity_info[block_id] += 1
    
    def get_rarest_needed_block(self) -> Optional[str]:
        """
        Seleciona o bloco mais raro que ainda não está disponível localmente.
        
        Returns:
            ID do bloco mais raro ou None se todos os blocos estiverem disponíveis
        """
        missing = self.get_missing_blocks()
        if not missing:
            return None
            
        # Encontra o bloco mais raro (menor contagem)
        rarest_block = min(
            missing, 
            key=lambda block_id: self.rarity_info.get(block_id, 0)
        )
        return rarest_block
    
    def reconstruct_file(self, output_path: str):
        """
        Reconstrói o arquivo completo a partir dos blocos disponíveis.
        
        Args:
            output_path: Caminho para salvar o arquivo reconstruído
            
        Raises:
            ValueError: Se nem todos os blocos estiverem disponíveis
        """
        if not self.is_complete():
            raise ValueError("Não é possível reconstruir o arquivo: blocos ausentes")
            
        # Considera que os blocos são numerados de forma sequencial
        sorted_blocks = sorted(self.total_blocks)
        
        with open(output_path, 'wb') as f:
            for block_id in sorted_blocks:
                f.write(self.blocks[block_id])