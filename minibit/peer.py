import socket
import threading
import time
import uuid
import logging
import os
import json
import random
from typing import Dict, Set, Optional, Tuple

from .block_manager import BlockManager
from .unchoke_manager import UnchokeManager
from .peer_connection import PeerConnection

class Peer:
    """
    Implementação do nó (peer) que compartilha e baixa arquivos.
    """
    def __init__(self, tracker_host, tracker_port, listen_port=0):
        self.peer_id = f"Peer-{uuid.uuid4().hex[:6]}"
        self.logger = logging.getLogger(self.peer_id)
        
        self.tracker_addr = (tracker_host, tracker_port)
        self.listen_port = listen_port
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None

        self.block_manager: Optional[BlockManager] = None
        self.unchoke_manager = UnchokeManager(self.peer_id, self.logger)
        
        # Estrutura: {peer_id: PeerConnection}
        self.connections: Dict[str, PeerConnection] = {}
        self.connections_lock = threading.Lock()
        
        # Estrutura: {peer_id: {'address': (ip, port), 'blocks': {block_ids}}}
        self.known_peers_info: Dict[str, Dict] = {}
        self.known_peers_lock = threading.Lock()

        self.running = False
        self.download_task: Optional[Dict] = None

    def start(self):
        """Inicia o servidor do peer para aceitar conexões de outros."""
        if self.running:
            return
        self.running = True
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind(('127.0.0.1', self.listen_port))
        # Pega a porta real caso 0 tenha sido usado
        self.listen_port = self.server_socket.getsockname()[1] 
        self.server_socket.listen(10)
        self.logger.info(f"Escutando na porta {self.listen_port}")
        
        self.server_thread = threading.Thread(target=self._accept_connections, daemon=True)
        self.server_thread.start()
        
        # Inicia threads de background para gerenciamento
        threading.Thread(target=self._manage_connections_and_requests, daemon=True).start()
        threading.Thread(target=self._run_unchoke_logic, daemon=True).start()

    def stop(self):
        """Para todas as operações do peer."""
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        
        with self.connections_lock:
            for conn in self.connections.values():
                conn.close()
            self.connections.clear()
        
        self.logger.info("Peer parado.")

    def share_file(self, file_path: str, block_size=16384): # 16KB
        """Configura o peer para ser um seeder de um novo arquivo."""
        file_name = os.path.basename(file_path)
        self.block_manager = BlockManager(file_name, block_size, self.logger)
        self.block_manager.load_from_file(file_path)
        
        self.logger.info(f"Compartilhando arquivo '{file_name}' com {self.block_manager.total_block_count} blocos.")
        
        # Registra no tracker
        self._register_with_tracker()

    def download_file(self, file_name: str, block_size=16384):
        """Configura o peer para ser um leecher de um arquivo."""
        self.download_task = {"file_name": file_name}
        self.block_manager = BlockManager(file_name, block_size, self.logger)
        self.logger.info(f"Preparando para baixar o arquivo '{file_name}'.")

        # Registra no tracker (com 0 blocos) e obtém a lista de peers
        self._register_with_tracker()
        self._update_peers_from_tracker()

    def is_download_complete(self):
        """Verifica se o download foi concluído."""
        if not self.block_manager:
            return False
        return self.block_manager.is_complete()

    # --- Métodos de Rede Internos ---

    def _accept_connections(self):
        """Loop para aceitar conexões de entrada de outros peers."""
        while self.running:
            try:
                conn_socket, addr = self.server_socket.accept()
                self.logger.info(f"Conexão de entrada de {addr}")
                # A conexão será gerenciada após a troca de mensagem 'handshake'
                threading.Thread(target=self._handle_incoming_connection, args=(conn_socket,), daemon=True).start()
            except OSError:
                break

    def _handle_incoming_connection(self, conn_socket: socket.socket):
        """Lida com a primeira mensagem de uma nova conexão para identificá-la."""
        try:
            # A primeira mensagem deve ser um 'handshake' para identificar o peer
            peer_conn = PeerConnection(address=conn_socket.getpeername(), sock=conn_socket, logger=self.logger)
            msg = peer_conn.read_message()

            if msg and msg.get('type') == 'handshake':
                incoming_peer_id = msg['peer_id']
                self.logger.info(f"Handshake recebido de {incoming_peer_id}")

                # Responde com nosso handshake
                peer_conn.send_message({'type': 'handshake', 'peer_id': self.peer_id})
                
                # Adiciona à lista de conexões
                with self.connections_lock:
                    self.connections[incoming_peer_id] = peer_conn

                # Inicia o loop de mensagens para esta nova conexão
                peer_conn.send_message({'type': 'have', 'blocks': list(self.block_manager.get_my_blocks())})
                self._message_loop(peer_conn, incoming_peer_id)
            else:
                self.logger.warning("Conexão de entrada sem handshake. Fechando.")
                conn_socket.close()
        except Exception as e:
            self.logger.error(f"Erro ao lidar com conexão de entrada: {e}")
            conn_socket.close()
            
    def _connect_to_peer(self, peer_id: str, address: Tuple[str, int]):
        """Estabelece uma conexão de saída para um novo peer."""
        with self.connections_lock:
            if peer_id in self.connections:
                return # Já conectado

        try:
            self.logger.info(f"Tentando conectar ao peer {peer_id} em {address}...")
            peer_conn = PeerConnection(address=address, logger=self.logger)
            if not peer_conn.connect():
                return

            # Envia handshake
            peer_conn.send_message({'type': 'handshake', 'peer_id': self.peer_id})
            response = peer_conn.read_message()
            if not response or response.get('type') != 'handshake':
                peer_conn.close()
                return

            # Adiciona à lista de conexões
            with self.connections_lock:
                self.connections[peer_id] = peer_conn
            
            # Solicita os blocos que ele tem
            peer_conn.send_message({'type': 'have', 'blocks': list(self.block_manager.get_my_blocks())})

            threading.Thread(target=self._message_loop, args=(peer_conn, peer_id), daemon=True).start()
            self.logger.info(f"Conexão estabelecida com {peer_id}")

        except Exception as e:
            self.logger.error(f"Falha ao conectar ao peer {peer_id}: {e}")

    def _message_loop(self, peer_conn: PeerConnection, peer_id: str):
        """Loop para processar mensagens de um peer específico."""
        while self.running and peer_conn.is_connected():
            try:
                msg = peer_conn.read_message()
                if not msg:
                    break # Conexão fechada

                msg_type = msg.get('type')

                if msg_type == 'have':
                    # Atualiza o que sabemos sobre os blocos do outro peer
                    self.block_manager.update_peer_blocks(peer_id, set(msg['blocks']))

                elif msg_type == 'request_block':
                    if self.unchoke_manager.is_unchoked(peer_id):
                        block_id = msg['block_id']
                        data = self.block_manager.get_block_data(block_id)
                        if data:
                            self.logger.info(f"Enviando bloco '{block_id}' para {peer_id}")
                            peer_conn.send_message({'type': 'block_data', 'block_id': block_id, 'data': data.hex()})

                elif msg_type == 'block_data':
                    block_id = msg['block_id']
                    data = bytes.fromhex(msg['data'])
                    if self.block_manager.add_block(block_id, data):
                        # Informa a todos que agora temos este bloco
                        self._broadcast_have_update()
                        # Se completou, reconstrói o arquivo
                        if self.block_manager.is_complete():
                            self.block_manager.reconstruct_file()
                            self.logger.info("="*50)
                            self.logger.info(f"DOWNLOAD COMPLETO! Arquivo '{self.block_manager.file_name}' salvo em 'downloads/'.")
                            self.logger.info("="*50)
                            # Agora este peer se torna um seeder
                            self.download_task = None
                
                elif msg_type == 'choke':
                    self.logger.info(f"Recebido CHOKE de {peer_id}")
                    peer_conn.set_choked_by_peer(True)
                
                elif msg_type == 'unchoke':
                    self.logger.info(f"Recebido UNCHOKE de {peer_id}")
                    peer_conn.set_choked_by_peer(False)

            except (ConnectionResetError, BrokenPipeError):
                self.logger.warning(f"Conexão com {peer_id} perdida.")
                break
            except Exception as e:
                self.logger.error(f"Erro no loop de mensagens com {peer_id}: {e}")
                break
        
        # Limpeza da conexão
        peer_conn.close()
        with self.connections_lock:
            if peer_id in self.connections:
                del self.connections[peer_id]
        with self.known_peers_lock:
            if peer_id in self.known_peers_info:
                del self.known_peers_info[peer_id]
        self.block_manager.remove_peer_blocks(peer_id)
        self.unchoke_manager.unregister_peer(peer_id)
        self.logger.info(f"Conexão com {peer_id} finalizada e limpa.")

    # --- Lógica de Gerenciamento e Estratégia ---

    def _manage_connections_and_requests(self):
        """Thread periódica para conectar a novos peers e solicitar blocos."""
        last_status_log_time = 0
        while self.running:
            time.sleep(5)
            # Atualiza a lista de peers do tracker periodicamente
            if self.download_task:
                 self._update_peers_from_tracker()

            # Conectar a novos peers da lista do tracker
            with self.known_peers_lock:
                all_known_peers = self.known_peers_info.copy()
            
            with self.connections_lock:
                connected_peers = self.connections.keys()

            for peer_id, info in all_known_peers.items():
                if peer_id not in connected_peers:
                    self._connect_to_peer(peer_id, info['address'])

            # Solicitar blocos dos peers que nos deram unchoke
            if self.download_task:
                self._request_blocks()
            
            # Exibir status do download a cada 10s
            if time.time() - last_status_log_time > 10:
                if self.block_manager and self.download_task:
                    self.logger.info(self.block_manager.get_status_string())
                    last_status_log_time = time.time()

    def _request_blocks(self):
        """Implementa a lógica 'rarest first' para solicitar blocos."""
        if not self.block_manager or self.block_manager.is_complete():
            return
            
        rarest_missing_blocks = self.block_manager.get_rarest_missing_blocks()
        if not rarest_missing_blocks:
            return

        with self.connections_lock:
            connections_copy = self.connections.copy()

        for block_id in rarest_missing_blocks:
            candidate_peers = []
            with self.known_peers_lock:
                # Usa o block_manager para saber quem tem o bloco
                peers_with_block = self.block_manager.peer_block_map.get(block_id, set())
                for peer_id in peers_with_block:
                    if peer_id in connections_copy and not connections_copy[peer_id].is_choked_by_peer():
                        candidate_peers.append(peer_id)
            
            if candidate_peers:
                chosen_peer_id = random.choice(candidate_peers)
                self.logger.info(f"Requisitando bloco (raro) '{block_id}' do peer {chosen_peer_id}")
                connections_copy[chosen_peer_id].send_message({'type': 'request_block', 'block_id': block_id})
                # Requisita um bloco por vez para não sobrecarregar
                return
        
        # Log se nenhum bloco puder ser requisitado
        if rarest_missing_blocks:
            self.logger.info(f"Faltam {len(rarest_missing_blocks)} blocos, mas não há peers desbloqueados para pedi-los agora.")

    def _run_unchoke_logic(self):
        """Thread periódica que executa a lógica de tit-for-tat."""
        while self.running:
            time.sleep(10) # A cada 10 segundos
            if not self.block_manager:
                continue

            self.logger.info("Executando lógica de unchoke...")
            
            interested_peers = []
            my_blocks = self.block_manager.get_my_blocks()
            
            with self.connections_lock:
                connected_peer_ids = list(self.connections.keys())

            for peer_id in connected_peer_ids:
                peer_blocks = self.block_manager.get_peer_blocks(peer_id)
                # Um peer está interessado se ele não tem todos os nossos blocos
                if not my_blocks.issubset(peer_blocks):
                    interested_peers.append(peer_id)
            
            if not interested_peers:
                self.logger.info("Nenhum peer interessado encontrado.")
                continue

            self.logger.info(f"Peers interessados encontrados: {interested_peers}")
            
            # Pede ao UnchokeManager para decidir quem desbloquear
            choke_list, unchoke_list = self.unchoke_manager.evaluate_peers(
                interested_peers,
                self.block_manager.get_block_rarity()
            )

            # Envia as mensagens de choke/unchoke
            with self.connections_lock:
                for peer_id in unchoke_list:
                    if peer_id in self.connections:
                        self.logger.info(f"Enviando UNCHOKE para: {peer_id}")
                        self.connections[peer_id].send_message({'type': 'unchoke'})
                for peer_id in choke_list:
                    if peer_id in self.connections:
                        self.logger.info(f"Enviando CHOKE para: {peer_id}")
                        self.connections[peer_id].send_message({'type': 'choke'})

    def _broadcast_have_update(self):
        """Informa a todos os peers conectados sobre os blocos que possuímos."""
        msg = {'type': 'have', 'blocks': list(self.block_manager.get_my_blocks())}
        with self.connections_lock:
            for conn in self.connections.values():
                conn.send_message(msg)
        # Também atualiza o tracker
        self._update_tracker_blocks()


    # --- Comunicação com o Tracker ---

    def _send_to_tracker(self, message: Dict) -> Optional[Dict]:
        """Função helper para enviar uma mensagem ao tracker e obter resposta."""
        try:
            with socket.create_connection(self.tracker_addr, timeout=5) as s:
                message['peer_id'] = self.peer_id
                msg_bytes = json.dumps(message).encode('utf-8')
                s.sendall(len(msg_bytes).to_bytes(4, 'big') + msg_bytes)

                raw_msglen = s.recv(4)
                if not raw_msglen: return None
                msglen = int.from_bytes(raw_msglen, 'big')
                response_bytes = s.recv(msglen)
                
                return json.loads(response_bytes.decode('utf-8'))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            self.logger.error(f"Não foi possível conectar ao tracker em {self.tracker_addr}: {e}")
            return None

    def _register_with_tracker(self):
        """Registra este peer no tracker."""
        if not self.block_manager: return
        
        message = {
            "command": "REGISTER",
            "file_name": self.block_manager.file_name,
            "address": ('127.0.0.1', self.listen_port),
            "blocks": list(self.block_manager.get_my_blocks())
        }
        self.logger.info(f"Registrando no tracker para o arquivo '{self.block_manager.file_name}'...")
        self._send_to_tracker(message)

    def _update_tracker_blocks(self):
        """Atualiza o tracker com la lista de blocos atual."""
        if not self.block_manager: return

        message = {
            "command": "UPDATE_BLOCKS",
            "file_name": self.block_manager.file_name,
            "blocks": list(self.block_manager.get_my_blocks())
        }
        self._send_to_tracker(message)

    def _update_peers_from_tracker(self):
        """Obtém e atualiza a lista de peers do tracker."""
        if not self.download_task: return
        
        message = {
            "command": "GET_PEERS",
            "file_name": self.download_task['file_name']
        }
        self.logger.info("Solicitando lista de peers do tracker...")
        response = self._send_to_tracker(message)

        if response and response.get('status') == 'ok':
            with self.known_peers_lock:
                for peer_info in response.get('peers', []):
                    peer_id = peer_info['peer_id']
                    if peer_id != self.peer_id and peer_id not in self.known_peers_info:
                        self.known_peers_info[peer_id] = {
                            "address": tuple(peer_info['address']),
                            "blocks": set(peer_info['blocks'])
                        }
                        # Alimenta o block_manager com a informação inicial de blocos dos outros
                        self.block_manager.update_peer_blocks(peer_id, set(peer_info['blocks']))
            self.logger.info(f"Tracker retornou {len(response.get('peers', []))} peers.")