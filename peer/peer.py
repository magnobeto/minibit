import os
import time
import socket
import random
import logging
import threading
import uuid
from typing import Dict, List, Set, Tuple, Optional, Any

from peer.block_manager import BlockManager
from peer.peer_connection import PeerConnection
from peer.unchoke_manager import UnchokeManager

class Peer:
    """
    Implementação do nó participante (peer) de uma rede P2P BitTorrent-like.
    Responsável pelo download/upload de blocos e pela comunicação com outros peers.
    """
    
    # Constantes
    MAX_CONNECTIONS = 10
    BLOCK_REQUEST_INTERVAL = 0.5  # segundos
    STATUS_UPDATE_INTERVAL = 5.0  # segundos
    
    def __init__(self, listen_port: int, tracker_address: Tuple[str, int], 
                 download_dir: str = "downloads"):
        """
        Inicializa um novo peer na rede.
        
        Args:
            listen_port: Porta para aceitar conexões de outros peers
            tracker_address: Endereço do tracker (host, porta)
            download_dir: Diretório para salvar os arquivos baixados
        """
        # Identificador único para este peer
        self.id = str(uuid.uuid4())[:8]
        self.listen_port = listen_port
        self.tracker_address = tracker_address
        self.download_dir = download_dir
        
        # Gerenciadores de componentes
        self.block_manager = BlockManager()
        self.unchoke_manager = UnchokeManager()
        
        # Estado interno
        self.running = False
        self.completed = False
        self.peers: Dict[str, Dict[str, Any]] = {}  # Informações sobre peers conhecidos
        self.connections: Dict[str, PeerConnection] = {}  # Conexões ativas
        
        # Threads
        self.server_thread: Optional[threading.Thread] = None
        self.client_thread: Optional[threading.Thread] = None
        self.tracker_thread: Optional[threading.Thread] = None
        
        # Locks para acesso thread-safe
        self.peers_lock = threading.Lock()
        self.connection_lock = threading.Lock()
        
        # Configuração de logging
        self.logger = self._setup_logger()
        
        # Garantir que o diretório de downloads existe
        os.makedirs(download_dir, exist_ok=True)
    
    def _setup_logger(self) -> logging.Logger:
        """
        Configura o logger para o peer.
        
        Returns:
            Instância configurada do logger
        """
        logger = logging.getLogger(f"Peer-{self.id}")
        logger.setLevel(logging.INFO)
        
        # Evitar duplicação de handlers
        if not logger.handlers:
            # Handler para saída no console
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(console_handler)
            
            # Handler para saída em arquivo
            file_handler = logging.FileHandler(f"peer-{self.id}.log")
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            logger.addHandler(file_handler)
        
        return logger
    
    def start(self, torrent_info: Dict[str, Any] = None) -> bool:
        """
        Inicia o peer, conectando ao tracker e começando a servir/baixar conteúdo.
        
        Args:
            torrent_info: Informações sobre o torrent a ser baixado
                         (None se apenas for iniciar o peer)
        
        Returns:
            True se o peer foi iniciado com sucesso, False caso contrário
        """
        if self.running:
            self.logger.warning("Peer já está em execução.")
            return False
        
        try:
            self.running = True
            
            # Iniciar o servidor para aceitar conexões
            self.server_thread = threading.Thread(target=self._run_server)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            # Se temos informações do torrent, iniciar o download
            if torrent_info:
                success = self._initialize_download(torrent_info)
                if not success:
                    self.logger.error("Falha ao inicializar download.")
                    self.stop()
                    return False
            
            # Iniciar thread para comunicação com o tracker
            self.tracker_thread = threading.Thread(target=self._tracker_communication_loop)
            self.tracker_thread.daemon = True
            self.tracker_thread.start()
            
            # Iniciar thread para gerenciamento de conexões e downloads
            self.client_thread = threading.Thread(target=self._client_loop)
            self.client_thread.daemon = True
            self.client_thread.start()
            
            self.logger.info(f"Peer iniciado com sucesso. ID: {self.id}, Porta: {self.listen_port}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao iniciar peer: {str(e)}")
            self.running = False
            return False
    
    def stop(self) -> None:
        """
        Para todas as operações do peer e fecha conexões.
        """
        if not self.running:
            return
            
        self.logger.info("Encerrando peer...")
        self.running = False
        
        # Fechar todas as conexões
        with self.connection_lock:
            for conn in list(self.connections.values()):
                conn.close()
            self.connections.clear()
        
        # Aguardar threads finalizarem (com timeout)
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
        
        if self.client_thread and self.client_thread.is_alive():
            self.client_thread.join(timeout=2.0)
            
        if self.tracker_thread and self.tracker_thread.is_alive():
            self.tracker_thread.join(timeout=2.0)
            
        self.logger.info("Peer encerrado.")
    
    def add_file(self, file_path: str, block_size: int = 1024*16) -> Dict[str, Any]:
        """
        Adiciona um arquivo para compartilhamento na rede.
        
        Args:
            file_path: Caminho do arquivo a ser compartilhado
            block_size: Tamanho dos blocos em bytes
            
        Returns:
            Informações do torrent gerado ou None se houver erro
        """
        try:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # Calcular número de blocos
            num_blocks = (file_size + block_size - 1) // block_size
            
            # Gerar IDs dos blocos
            block_ids = [f"{file_name}_{i}" for i in range(num_blocks)]
            
            # Inicializar o block manager com todos os blocos
            self.block_manager.load_initial_blocks(block_ids, len(block_ids))
            
            # Ler arquivo e adicionar blocos
            with open(file_path, 'rb') as f:
                for i, block_id in enumerate(block_ids):
                    data = f.read(block_size)
                    if not data:
                        break
                    self.block_manager.add_block(block_id, data)
            
            torrent_info = {
                "file_name": file_name,
                "file_size": file_size,
                "block_size": block_size,
                "num_blocks": num_blocks,
                "block_ids": block_ids
            }
            
            self.logger.info(f"Arquivo adicionado: {file_name}, {num_blocks} blocos")
            
            # Se o peer já está rodando, atualizar o tracker
            if self.running:
                self._update_tracker(torrent_info)
            
            return torrent_info
            
        except Exception as e:
            self.logger.error(f"Erro ao adicionar arquivo: {str(e)}")
            return None
    
    def download_file(self, torrent_info: Dict[str, Any]) -> bool:
        """
        Inicia o download de um arquivo usando as informações do torrent.
        
        Args:
            torrent_info: Informações do torrent
            
        Returns:
            True se o download foi iniciado com sucesso, False caso contrário
        """
        if not self.running:
            self.logger.error("Peer não está em execução.")
            return self.start(torrent_info)
        
        return self._initialize_download(torrent_info)
    
    def get_download_status(self) -> Dict[str, Any]:
        """
        Retorna o status atual do download.
        
        Returns:
            Dicionário com informações sobre o progresso do download
        """
        if not hasattr(self, 'torrent_info') or not self.torrent_info:
            return {"status": "idle", "progress": 0}
        
        total_blocks = len(self.torrent_info["block_ids"])
        downloaded_blocks = len(self.block_manager.get_blocks())
        
        progress = (downloaded_blocks / total_blocks) * 100 if total_blocks > 0 else 0
        
        return {
            "status": "completed" if self.completed else "downloading",
            "file_name": self.torrent_info.get("file_name", "unknown"),
            "progress": progress,
            "downloaded_blocks": downloaded_blocks,
            "total_blocks": total_blocks,
            "active_connections": len(self.connections),
            "known_peers": len(self.peers)
        }
    
    def _initialize_download(self, torrent_info: Dict[str, Any]) -> bool:
        """
        Inicializa o processo de download com base nas informações do torrent.
        
        Args:
            torrent_info: Informações do torrent
            
        Returns:
            True se a inicialização foi bem-sucedida, False caso contrário
        """
        try:
            self.torrent_info = torrent_info
            self.completed = False
            
            # Configurar o gerenciador de blocos
            block_ids = torrent_info["block_ids"]
            self.block_manager = BlockManager()
            self.block_manager.load_initial_blocks(block_ids)
            
            # Contatar o tracker para obter a lista inicial de peers
            success = self._update_tracker(torrent_info)
            if not success:
                self.logger.error("Falha ao contatar o tracker.")
                return False
                
            self.logger.info(f"Download iniciado: {torrent_info['file_name']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao inicializar download: {str(e)}")
            return False
    
    def _run_server(self) -> None:
        """
        Thread que aceita conexões de outros peers.
        """
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('', self.listen_port))
            server_socket.settimeout(1.0)  # Timeout para permitir verificação de self.running
            server_socket.listen(5)
            
            self.logger.info(f"Servidor iniciado na porta {self.listen_port}")
            
            while self.running:
                try:
                    client_socket, address = server_socket.accept()
                    client_thread = threading.Thread(
                        target=self._handle_incoming_connection,
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Erro no servidor: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Erro fatal no servidor: {str(e)}")
        finally:
            try:
                server_socket.close()
            except:
                pass
    
    def _handle_incoming_connection(self, client_socket: socket.socket, address: Tuple[str, int]) -> None:
        """
        Processa uma nova conexão de entrada.
        
        Args:
            client_socket: Socket do cliente conectado
            address: Endereço do cliente (host, porta)
        """
        peer_conn = None
        try:
            self.logger.info(f"Nova conexão de {address}")
            
            # Criar objeto de conexão
            peer_addr = (address[0], address[1])
            peer_conn = PeerConnection(peer_addr)
            peer_conn.socket = client_socket
            peer_conn.file_stream = client_socket.makefile(mode='rb')
            peer_conn.connected = True
            
            # Receber mensagem de registro
            msg_type, payload = peer_conn._read_message()
            
            if msg_type != PeerConnection.MSG_REGISTER:
                self.logger.warning("Primeira mensagem não é registro. Fechando conexão.")
                return
                
            # Extrair informações do peer
            peer_id = payload.get("peer_id")
            available_blocks = set(payload.get("blocks", []))
            
            if not peer_id:
                self.logger.warning("ID do peer não fornecido. Fechando conexão.")
                return
                
            # Responder com nossos blocos disponíveis
            our_blocks = list(self.block_manager.get_blocks())
            response = {
                "peer_id": self.id,
                "blocks": our_blocks
            }
            peer_conn._send_message(PeerConnection.MSG_HAVE_BLOCKS, response)
            
            # Registrar a conexão
            with self.connection_lock:
                if len(self.connections) >= self.MAX_CONNECTIONS:
                    # Se já atingiu o limite, fecha a conexão mais antiga que não esteja unchoked
                    oldest_conn = None
                    oldest_time = float('inf')
                    
                    for pid, conn in self.connections.items():
                        if not self.unchoke_manager.is_unchoked(pid):
                            # Verificar tempo (usando peer_id como estimativa)
                            if pid < oldest_time:
                                oldest_time = pid
                                oldest_conn = pid
                    
                    if oldest_conn:
                        old_conn = self.connections.pop(oldest_conn, None)
                        if old_conn:
                            old_conn.close()
                
                self.connections[peer_id] = peer_conn
            
            # Registrar o peer
            with self.peers_lock:
                self.peers[peer_id] = {
                    "address": peer_addr,
                    "available_blocks": available_blocks,
                    "last_seen": time.time()
                }
            
            # Registrar no unchoke manager
            self.unchoke_manager.register_peer(peer_id)
            
            # Atualizar informações de raridade no block manager
            self.block_manager.update_rarity_info(peer_id, available_blocks)
            
            # Loop de processamento de mensagens
            self._process_peer_messages(peer_conn, peer_id)
            
        except Exception as e:
            self.logger.error(f"Erro no processamento da conexão de {address}: {str(e)}")
        finally:
            if peer_conn and peer_conn.peer_id in self.connections:
                with self.connection_lock:
                    self.connections.pop(peer_conn.peer_id, None)
                peer_conn.close()
    
    def _process_peer_messages(self, peer_conn: PeerConnection, peer_id: str) -> None:
        """
        Processa mensagens recebidas de um peer conectado.
        
        Args:
            peer_conn: Objeto de conexão com o peer
            peer_id: ID do peer
        """
        while self.running and peer_conn.is_connected():
            try:
                msg_type, payload = peer_conn.read_message()
                
                if msg_type == PeerConnection.MSG_REQUEST_BLOCK:
                    block_id = payload.get("block_id")
                    
                    # Verificar se o peer está unchoked
                    if not self.unchoke_manager.is_unchoked(peer_id):
                        self.logger.debug(f"Bloqueando solicitação do peer {peer_id}: choked")
                        continue
                    
                    # Verificar se temos o bloco
                    if not block_id or not self.block_manager.has_block(block_id):
                        continue
                        
                    # Enviar o bloco
                    block_data = self.block_manager.get_block_data(block_id)
                    if block_data:
                        peer_conn.send_block(block_id, block_data)
                
                elif msg_type == PeerConnection.MSG_BLOCK_DATA:
                    block_id = payload.get("block_id")
                    block_data = payload.get("data")
                    
                    if not block_id or not block_data:
                        continue
                        
                    # Adicionar o bloco ao gerenciador
                    if self.block_manager.add_block(block_id, block_data):
                        # Registrar o download para o unchoke manager
                        self.unchoke_manager.record_download(peer_id, len(block_data))
                        
                        # Verificar se o download está completo
                        if self.block_manager.is_complete():
                            self._handle_download_completion()
                            
                        # Notificar outros peers que temos este bloco
                        self._broadcast_have_block(block_id)
                
                elif msg_type == PeerConnection.MSG_HAVE_BLOCKS:
                    blocks = set(payload.get("blocks", []))
                    
                    # Atualizar informações do peer
                    with self.peers_lock:
                        if peer_id in self.peers:
                            self.peers[peer_id]["available_blocks"] = blocks
                            self.peers[peer_id]["last_seen"] = time.time()
                    
                    # Atualizar informações de raridade
                    self.block_manager.update_rarity_info(peer_id, blocks)
                    
                    # Marcar como interessado se o peer tem blocos que precisamos
                    missing_blocks = self.block_manager.get_missing_blocks()
                    is_interested = bool(missing_blocks.intersection(blocks))
                    self.unchoke_manager.set_peer_interested(peer_id, is_interested)
                
                elif msg_type == PeerConnection.MSG_CHOKE:
                    peer_conn.set_choked_status(True)
                    
                elif msg_type == PeerConnection.MSG_UNCHOKE:
                    peer_conn.set_choked_status(False)
                
            except Exception as e:
                self.logger.error(f"Erro no processamento de mensagem do peer {peer_id}: {str(e)}")
                break
    
    def _client_loop(self) -> None:
        """
        Thread principal do cliente que gerencia conexões e solicita blocos.
        """
        last_block_request_time = 0
        last_status_update_time = 0
        last_unchoke_evaluation_time = 0
        
        while self.running:
            current_time = time.time()
            
            try:
                # Avaliar peers para choke/unchoke periodicamente
                if current_time - last_unchoke_evaluation_time >= 5.0:
                    self.unchoke_manager.evaluate_peers()
                    last_unchoke_evaluation_time = current_time
                    
                    # Aplicar decisões de choke/unchoke
                    self._apply_choke_decisions()
                
                # Conectar a novos peers periodicamente
                self._manage_connections()
                
                # Solicitar blocos periodicamente
                if current_time - last_block_request_time >= self.BLOCK_REQUEST_INTERVAL:
                    self._request_missing_blocks()
                    last_block_request_time = current_time
                
                # Atualizar e exibir status periodicamente
                if current_time - last_status_update_time >= self.STATUS_UPDATE_INTERVAL:
                    self._log_status()
                    last_status_update_time = current_time
                
                # Pequena pausa para evitar CPU 100%
                time.sleep(0.05)
                
            except Exception as e:
                self.logger.error(f"Erro no loop do cliente: {str(e)}")
                time.sleep(1)
    
    def _tracker_communication_loop(self) -> None:
        """
        Thread responsável pela comunicação periódica com o tracker.
        """
        while self.running:
            try:
                if hasattr(self, 'torrent_info') and self.torrent_info:
                    self._update_tracker(self.torrent_info)
                    
                # Atualizar a cada 30 segundos
                for _ in range(30):
                    if not self.running:
                        break
                    time.sleep(1)
            
            except Exception as e:
                self.logger.error(f"Erro na comunicação com tracker: {str(e)}")
                time.sleep(5)
    
    def _update_tracker(self, torrent_info: Dict[str, Any]) -> bool:
        """
        Atualiza o tracker sobre o status do peer e obtém a lista de peers.
        
        Args:
            torrent_info: Informações do torrent
            
        Returns:
            True se a atualização foi bem-sucedida, False caso contrário
        """
        try:
            # Em uma implementação real, aqui seria uma requisição HTTP ou TCP
            # ao tracker. Para este exemplo, simularemos uma resposta.
            
            # Supondo que o tracker retorne uma lista de peers ativos
            tracker_response = {
                "peers": [
                    {"id": f"peer_{i}", "host": "127.0.0.1", "port": 9000+i}
                    for i in range(1, 5)
                ]
            }
            
            # Processar a lista de peers
            for peer_info in tracker_response["peers"]:
                peer_id = peer_info["id"]
                peer_addr = (peer_info["host"], peer_info["port"])
                
                # Não adicionar a si mesmo
                if peer_id == self.id:
                    continue
                
                # Adicionar à lista de peers conhecidos
                with self.peers_lock:
                    if peer_id not in self.peers:
                        self.peers[peer_id] = {
                            "address": peer_addr,
                            "available_blocks": set(),
                            "last_seen": time.time()
                        }
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao atualizar tracker: {str(e)}")
            return False
    
    def _manage_connections(self) -> None:
        """
        Gerencia conexões ativas, estabelecendo novas quando necessário.
        """
        # Se já atingiu o limite de conexões, não fazer nada
        with self.connection_lock:
            if len(self.connections) >= self.MAX_CONNECTIONS:
                return
        
        # Obter peers conhecidos que não estamos conectados
        unconnected_peers = []
        with self.peers_lock:
            for peer_id, peer_info in self.peers.items():
                with self.connection_lock:
                    if peer_id not in self.connections:
                        unconnected_peers.append((peer_id, peer_info["address"]))
        
        # Tentar conectar a novos peers
        for peer_id, peer_addr in unconnected_peers:
            if not self.running:
                break
                
            with self.connection_lock:
                if len(self.connections) >= self.MAX_CONNECTIONS:
                    break
                    
                if peer_id in self.connections:
                    continue
            
            # Tentar estabelecer conexão
            self._connect_to_peer(peer_id, peer_addr)
    
    def _connect_to_peer(self, peer_id: str, peer_addr: Tuple[str, int]) -> bool:
        """
        Estabelece conexão com um peer específico.
        
        Args:
            peer_id: ID do peer
            peer_addr: Endereço do peer (host, porta)
            
        Returns:
            True se a conexão foi estabelecida com sucesso, False caso contrário
        """
        try:
            peer_conn = PeerConnection(peer_addr, peer_id)
            
            # Tentar conectar
            if not peer_conn.connect():
                return False
                
            # Registrar-se com o peer
            our_blocks = list(self.block_manager.get_blocks())
            if not peer_conn.register(self.id, our_blocks):
                peer_conn.close()
                return False
            
            # Adicionar à lista de conexões
            with self.connection_lock:
                self.connections[peer_id] = peer_conn
                
            # Iniciar thread para processar mensagens
            client_thread = threading.Thread(
                target=self._process_peer_messages,
                args=(peer_conn, peer_id)
            )
            client_thread.daemon = True
            client_thread.start()
            
            # Registrar no unchoke manager
            self.unchoke_manager.register_peer(peer_id)
            
            self.logger.info(f"Conexão estabelecida com peer {peer_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao conectar ao peer {peer_id}: {str(e)}")
            return False
    
    def _request_missing_blocks(self) -> None:
        """
        Solicita blocos ausentes de peers conectados.
        """
        # Se já completou o download, não fazer nada
        if self.completed:
            return
            
        # Obter blocos ausentes
        missing_blocks = list(self.block_manager.get_missing_blocks())
        if not missing_blocks:
            return
            
        # Obter lista de peers unchoked
        unchoked_peers = self.unchoke_manager.get_unchoked_peers()
        if not unchoked_peers:
            return
            
        # Para cada peer não bloqueado, solicitar um bloco
        for peer_id in unchoked_peers:
            # Verificar se o peer está conectado
            peer_conn = None
            with self.connection_lock:
                peer_conn = self.connections.get(peer_id)
                
            if not peer_conn or not peer_conn.is_connected() or peer_conn.is_choked():
                continue
                
            # Verificar quais blocos ausentes o peer tem
            available_blocks = set()
            with self.peers_lock:
                if peer_id in self.peers:
                    available_blocks = self.peers[peer_id].get("available_blocks", set())
            
            # Filtrar blocos que o peer tem
            mutual_blocks = set(missing_blocks).intersection(available_blocks)
            if not mutual_blocks:
                continue
                
            # Selecionar o bloco mais raro
            rarest_block = self.block_manager.get_rarest_needed_block()
            if not rarest_block or rarest_block not in mutual_blocks:
                # Fallback para seleção aleatória
                block_id = random.choice(list(mutual_blocks))
            else:
                block_id = rarest_block
                
            # Solicitar o bloco
            block_data = peer_conn.request_block(block_id)
            if block_data:
                # Adicionar o bloco recebido
                if self.block_manager.add_block(block_id, block_data):
                    # Registrar o download para o unchoke manager
                    self.unchoke_manager.record_download(peer_id, len(block_data))
                    
                    # Verificar se o download está completo
                    if self.block_manager.is_complete():
                        self._handle_download_completion()
                        
                    # Notificar outros peers que temos este bloco
                    self._broadcast_have_block(block_id)
    
    def _apply_choke_decisions(self) -> None:
        """
        Aplica as decisões de choke/unchoke aos peers conectados.
        """
        unchoked_peers = set(self.unchoke_manager.get_unchoked_peers())
        
        # Para cada conexão, aplicar o status de choke
        with self.connection_lock:
            for peer_id, conn in self.connections.items():
                should_be_unchoked = peer_id in unchoked_peers
                is_unchoked = not conn.is_choked()
                
                # Se o status mudou, enviar mensagem
                if should_be_unchoked != is_unchoked:
                    if should_be_unchoked:
                        conn.send_unchoke()
                        conn.set_choked_status(False)
                    else:
                        conn.send_choke()
                        conn.set_choked_status(True)
    
    def _broadcast_have_block(self, block_id: str) -> None:
        """
        Notifica todos os peers conectados sobre um novo bloco disponível.
        
        Args:
            block_id: ID do bloco adicionado
        """
        our_blocks = list(self.block_manager.get_blocks())
        
        with self.connection_lock:
            for peer_id, conn in self.connections.items():
                try:
                    conn.send_have_blocks(our_blocks)
                except Exception as e:
                    self.logger.error(f"Erro ao enviar HAVE_BLOCKS para {peer_id}: {str(e)}")
    
    def _handle_download_completion(self) -> None:
        """
        Processa a conclusão do download, reconstruindo o arquivo.
        """
        if self.completed:
            return
            
        try:
            # Marcar como completo
            self.completed = True
            
            # Obter informações do torrent
            file_name = self.torrent_info.get("file_name", "downloaded_file")
            output_path = os.path.join(self.download_dir, file_name)
            
            # Reconstruir o arquivo
            self.block_manager.reconstruct_file(output_path)
            
            self.logger.info(f"Download completo! Arquivo salvo em: {output_path}")
            
            # Notificar o tracker (em uma implementação real)
            
        except Exception as e:
            self.completed = False
            self.logger.error(f"Erro ao finalizar download: {str(e)}")
    
    def _log_status(self) -> None:
        """
        Registra o status atual do download no log.
        """
        if not hasattr(self, 'torrent_info') or not self.torrent_info:
            return
            
        status = self.get_download_status()
        
        self.logger.info(
            f"Status: {status['status']} | "
            f"Progresso: {status['progress']:.1f}% | "
            f"{status['downloaded_blocks']}/{status['total_blocks']} blocos | "
            f"Conexões: {status['active_connections']}"
        )