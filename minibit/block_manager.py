import os
import logging
from typing import Set, Dict, List, Optional, Tuple

class BlockManager:
    """
    Gerencia os blocos de um arquivo: lê, armazena, reconstrói e
    rastreia a raridade dos blocos na rede.
    """
    def __init__(self, file_name: str, block_size: int, logger: logging.Logger):
        self.file_name = file_name
        self.block_size = block_size
        self.logger = logger
        
        self.my_blocks: Dict[str, bytes] = {}
        self.total_block_count = 0
        self.all_block_ids: List[str] = []

        # Estrutura: {block_id: {peer_id1, peer_id2, ...}}
        self.peer_block_map: Dict[str, Set[str]] = {}
        
        self.download_dir = "downloads"
        os.makedirs(self.download_dir, exist_ok=True)

    def load_from_file(self, file_path: str):
        """Divide um arquivo em blocos e os carrega na memória."""
        try:
            file_size = os.path.getsize(file_path)
            self.total_block_count = (file_size + self.block_size - 1) // self.block_size
            
            base_name = os.path.basename(file_path)
            self.all_block_ids = [f"{base_name}_{i}" for i in range(self.total_block_count)]

            with open(file_path, 'rb') as f:
                for i, block_id in enumerate(self.all_block_ids):
                    data = f.read(self.block_size)
                    self.my_blocks[block_id] = data
            self.logger.info(f"Arquivo '{file_path}' carregado com {len(self.my_blocks)} blocos.")
        except FileNotFoundError:
            self.logger.error(f"Arquivo não encontrado: {file_path}")

    def add_block(self, block_id: str, data: bytes) -> bool:
        """Adiciona um bloco recém-baixado."""
        if block_id in self.my_blocks:
            return False
            
        self.my_blocks[block_id] = data
        self.logger.info(f"Recebido bloco '{block_id}'")
        return True

    def get_block_data(self, block_id: str) -> Optional[bytes]:
        """Retorna os dados de um bloco que o peer possui."""
        return self.my_blocks.get(block_id)

    def get_my_blocks(self) -> Set[str]:
        """Retorna os IDs de todos os blocos que o peer possui."""
        return set(self.my_blocks.keys())

    def get_missing_blocks(self) -> Set[str]:
        """Retorna os IDs dos blocos que faltam para completar o arquivo."""
        if not self.all_block_ids:
            return set()
        return set(self.all_block_ids) - self.get_my_blocks()
    
    def is_complete(self) -> bool:
        """Verifica se o peer possui todos os blocos do arquivo."""
        if self.total_block_count == 0 and len(self.all_block_ids) > 0:
             self.total_block_count = len(self.all_block_ids)

        return len(self.my_blocks) > 0 and len(self.my_blocks) == self.total_block_count
    
    def reconstruct_file(self):
        """Monta o arquivo final a partir dos blocos baixados."""
        if not self.is_complete():
            self.logger.error("Tentativa de reconstruir arquivo incompleto.")
            return

        output_path = os.path.join(self.download_dir, self.file_name)
        self.logger.info(f"Reconstruindo arquivo em '{output_path}'...")
        
        # Ordena os blocos pelo seu índice numérico
        sorted_block_ids = sorted(self.my_blocks.keys(), key=lambda x: int(x.split('_')[-1]))

        try:
            with open(output_path, 'wb') as f:
                for block_id in sorted_block_ids:
                    f.write(self.my_blocks[block_id])
            self.logger.info(f"Arquivo '{self.file_name}' reconstruído com sucesso.")
        except IOError as e:
            self.logger.error(f"Erro ao escrever arquivo reconstruído: {e}")

    # --- Lógica de Rastreamento de Raridade ---

    def update_peer_blocks(self, peer_id: str, their_blocks: Set[str]):
        """Atualiza quais blocos um peer específico possui."""
        # Se for a primeira vez que vemos os blocos deste peer, inicializa total_block_count
        if self.total_block_count == 0 and their_blocks:
            self.total_block_count = len(their_blocks)
            self.all_block_ids = sorted(list(their_blocks), key=lambda x: int(x.split('_')[-1]))

        # Remove o peer de todos os blocos que ele não tem mais
        for block_id, peers in self.peer_block_map.items():
            if peer_id in peers and block_id not in their_blocks:
                peers.remove(peer_id)
        
        # Adiciona o peer aos novos blocos
        for block_id in their_blocks:
            if block_id not in self.peer_block_map:
                self.peer_block_map[block_id] = set()
            self.peer_block_map[block_id].add(peer_id)
            
    def remove_peer_blocks(self, peer_id: str):
        """Remove todas as informações de blocos de um peer desconectado."""
        for peers in self.peer_block_map.values():
            if peer_id in peers:
                peers.remove(peer_id)

    def get_block_rarity(self) -> Dict[str, int]:
        """Calcula a raridade de cada bloco (quantos peers o têm)."""
        return {block_id: len(peers) for block_id, peers in self.peer_block_map.items()}

    def get_rarest_missing_blocks(self) -> List[str]:
        """Retorna uma lista de blocos ausentes, do mais raro para o mais comum."""
        missing = self.get_missing_blocks()
        if not missing:
            return []
            
        rarity = self.get_block_rarity()
        # Ordena os blocos ausentes pela sua raridade (menor primeiro)
        # O valor default 0 para raridade significa que nenhum peer conhecido o tem
        return sorted(list(missing), key=lambda block: rarity.get(block, 0))

    def get_peer_blocks(self, peer_id: str) -> Set[str]:
        """Retorna o conjunto de blocos que um peer específico é conhecido por ter."""
        peer_blocks = set()
        for block_id, peers_with_block in self.peer_block_map.items():
            if peer_id in peers_with_block:
                peer_blocks.add(block_id)
        return peer_blocks

    def get_status_string(self) -> str:
        """Retorna uma string formatada com o status atual do download."""
        if self.total_block_count == 0:
            return "Status: idle | Aguardando informações do arquivo..."
        
        progress = (len(self.my_blocks) / self.total_block_count) * 100
        status = "completed" if self.is_complete() else "downloading"
        
        return (f"Status: {status} | Progresso: {progress:.1f}% | "
                f"{len(self.my_blocks)}/{self.total_block_count} blocos")