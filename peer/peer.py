import socket
import threading
import time
import random
import logging
from typing import Set, Dict, List, Optional, Tuple, Any

class Peer:
    """
    Implementa um peer na rede MiniBit.
    
    Responsável por:
    - Gerenciar conexões com outros peers
    - Solicitar e compartilhar blocos de arquivo
    - Implementar estratégias de rarest first e tit-for-tat
    - Manter registros de peers conectados e desbloqueados
    """
    
    def __init__(self, peer_id: str, tracker_address: Tuple[str, int]):
        """
        Inicializa um peer com identificador único e endereço do tracker.
        """
        self.peer_id = peer_id
        self.tracker_address = tracker_address
        self.block_manager = BlockManager()
        self.unchoke_manager = UnchokeManager(self)
        self.peers = set()  # Conjunto de peers conhecidos
        
        # Valores de configuração
        self.port = random.randint(10000, 60000)
        self.host = "127.0.0.1"  # IP local para simulação
        
        # Controle de conexão
        self.running = False
        self.server_socket = None
        self.peer_connections = {}  # Mapeia peer_id para conexões
        self.file_completed = False
        
        # Threads
        self.server_thread = None
        self.unchoke_thread = None
        self.tracker_update_thread = None
        
        # Locks
        self.peers_lock = threading.Lock()
        self.connections_lock = threading.Lock()
        
        # Configuração de logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"Peer-{peer_id}")
    
    def join_network(self):
        """
        Registra o peer no tracker e inicia o processo de conexão à rede.
        """
        self.logger.info(f"Peer {self.peer_id} iniciando conexão com a rede")
        
        # Inicializa conexão com o tracker
        try:
            # Cria socket para comunicar com o tracker
            tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tracker_socket.connect(self.tracker_address)
            
            # Prepara mensagem de registro
            blocks = self.block_manager.get_blocks()
            payload = {
                "peer_id": self.peer_id,
                "ip": self.host,
                "port": self.port,
                "blocks": list(blocks)
            }
            
            # Envia registro para o tracker
            message = Protocol.create_message(Protocol.REGISTER, payload)
            tracker_socket.sendall(message)
            
            # Recebe resposta do tracker (lista de peers)
            response_type, response_payload = Protocol.read_message_from_stream(tracker_socket.makefile(mode='rb'))
            tracker_socket.close()
            
            if response_type != Protocol.PEER_LIST:
                self.logger.error("Resposta inesperada do tracker")
                return False
            
            # Processa lista de peers recebida
            new_peers = response_payload.get("peers", [])
            self.logger.info(f"Recebidos {len(new_peers)} peers do tracker")
            
            # Adiciona peers à lista local
            with self.peers_lock:
                for peer_data in new_peers:
                    peer_id = peer_data[0]
                    peer_ip = peer_data[1]
                    peer_port = peer_data[2]
                    self.peers.add((peer_id, peer_ip, peer_port))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao conectar ao tracker: {str(e)}")
            return False
    
    def run(self):
        """
        Inicia o loop principal do peer, gerenciando conexões e troca de blocos.
        """
        self.running = True
        
        # Inicia servidor para aceitar conexões
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1)  # Timeout para permitir encerramento controlado
        
        # Cria threads
        self.server_thread = threading.Thread(target=self._accept_connections)
        self.unchoke_thread = threading.Thread(target=self._run_unchoke_process)
        self.tracker_update_thread = threading.Thread(target=self._update_tracker_periodically)
        
        # Inicia threads
        self.server_thread.start()
        self.unchoke_thread.start()
        self.tracker_update_thread.start()
        
        # Conecta aos peers conhecidos
        self._connect_to_peers()
        
        # Enquanto estiver em execução, faz requisições de blocos
        while self.running and not self.file_completed:
            try:
                # Verifica se já tem todos os blocos
                if self.block_manager.is_complete():
                    self.logger.info("Arquivo completo! Preparando para encerramento...")
                    self.file_completed = True
                    break
                
                # Seleciona próximo bloco para solicitar usando rarest first
                next_block = self.block_manager.get_rarest_needed_block()
                if next_block is None:
                    time.sleep(1)  # Espera antes de tentar novamente
                    continue
                
                # Encontra peer desbloqueado que possui esse bloco
                peer_id = self.unchoke_manager.get_peer_with_block(next_block)
                if not peer_id:
                    time.sleep(0.5)  # Espera antes de tentar novamente
                    continue
                
                # Solicita bloco ao peer
                self._request_block(peer_id, next_block)
                
                # Pequena pausa para controlar a taxa de solicitações
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Erro no loop principal: {str(e)}")
                time.sleep(1)
        
        if self.file_completed:
            self.shutdown()
    
    def shutdown(self):
        """
        Reconstrói o arquivo completo e encerra ordenadamente o peer.
        """
        self.logger.info("Iniciando processo de desligamento")
        self.running = False
        
        # Espera pelas threads
        if self.server_thread:
            self.server_thread.join(timeout=2)
        if self.unchoke_thread:
            self.unchoke_thread.join(timeout=2)
        if self.tracker_update_thread:
            self.tracker_update_thread.join(timeout=2)
        
        # Fecha o socket do servidor
        if self.server_socket:
            self.server_socket.close()
        
        # Fecha as conexões com peers
        with self.connections_lock:
            for conn in self.peer_connections.values():
                try:
                    conn['socket'].close()
                except:
                    pass
            self.peer_connections.clear()
        
        # Reconstrói o arquivo se estiver completo
        if self.block_manager.is_complete():
            try:
                output_file = f"reconstructed_{self.peer_id}.txt"
                self.block_manager.reconstruct_file(output_file)
                self.logger.info(f"Arquivo reconstruído com sucesso: {output_file}")
            except Exception as e:
                self.logger.error(f"Erro ao reconstruir arquivo: {str(e)}")
        
        self.logger.info(f"Peer {self.peer_id} encerrado")
    
    def _accept_connections(self):
        """
        Thread que aceita conexões de entrada de outros peers.
        """
        self.logger.info(f"Servidor iniciado em {self.host}:{self.port}")
        
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                client_thread = threading.Thread(target=self._handle_peer_connection, args=(client_socket, addr))
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erro ao aceitar conexão: {str(e)}")
    
    def _handle_peer_connection(self, client_socket, addr):
        """
        Gerencia uma conexão de entrada de outro peer.
        """
        try:
            # Configura o socket
            client_socket.settimeout(10)
            client_file = client_socket.makefile(mode='rb')
            
            # Espera pela mensagem inicial
            msg_type, payload = Protocol.read_message_from_stream(client_file)
            
            if msg_type == Protocol.REGISTER:
                peer_id = payload.get("peer_id")
                peer_blocks = set(payload.get("blocks", []))
                
                # Registra a conexão
                with self.connections_lock:
                    self.peer_connections[peer_id] = {
                        'socket': client_socket,
                        'file': client_file,
                        'addr': addr,
                        'blocks': peer_blocks,
                        'last_activity': time.time()
                    }
                
                self.logger.info(f"Conexão de entrada estabelecida com peer {peer_id}")
                
                # Responde com os blocos que este peer possui
                response_payload = {
                    "peer_id": self.peer_id,
                    "blocks": list(self.block_manager.get_blocks())
                }
                response = Protocol.create_message(Protocol.HAVE_BLOCKS, response_payload)
                client_socket.sendall(response)
                
                # Atualiza o gerenciador de unchoke
                self.unchoke_manager.add_peer(peer_id, peer_blocks)
                
                # Continua processando mensagens deste peer
                self._process_peer_messages(peer_id, client_socket, client_file)
            else:
                self.logger.warning(f"Mensagem inicial inesperada: {msg_type}")
                client_socket.close()
                
        except Exception as e:
            self.logger.error(f"Erro ao tratar conexão do peer {addr}: {str(e)}")
            try:
                client_socket.close()
            except:
                pass
    
    def _process_peer_messages(self, peer_id, socket, file):
        """
        Processa mensagens de um peer conectado.
        """
        while self.running:
            try:
                msg_type, payload = Protocol.read_message_from_stream(file)
                if not msg_type:
                    break
                
                with self.connections_lock:
                    if peer_id in self.peer_connections:
                        self.peer_connections[peer_id]['last_activity'] = time.time()
                
                # Processa mensagem de acordo com o tipo
                if msg_type == Protocol.REQUEST_BLOCK:
                    block_id = payload.get("block_id")
                    self._handle_block_request(peer_id, socket, block_id)
                    
                elif msg_type == Protocol.BLOCK_DATA:
                    block_id = payload.get("block_id")
                    block_data = payload.get("data")
                    self._handle_block_data(peer_id, block_id, block_data)
                    
                elif msg_type == Protocol.HAVE_BLOCKS:
                    blocks = set(payload.get("blocks", []))
                    self._handle_have_blocks(peer_id, blocks)
                    
                elif msg_type == Protocol.UNCHOKE:
                    self._handle_unchoke(peer_id)
                    
                elif msg_type == Protocol.CHOKE:
                    self._handle_choke(peer_id)
                    
            except Exception as e:
                self.logger.error(f"Erro ao processar mensagens do peer {peer_id}: {str(e)}")
                break
        
        # Conexão encerrada
        with self.connections_lock:
            if peer_id in self.peer_connections:
                self.logger.info(f"Conexão encerrada com peer {peer_id}")
                self.peer_connections[peer_id]['socket'].close()
                del self.peer_connections[peer_id]
        
        self.unchoke_manager.remove_peer(peer_id)
    
    def _connect_to_peers(self):
        """
        Estabelece conexões com peers conhecidos.
        """
        with self.peers_lock:
            peers_to_connect = list(self.peers)
        
        for peer_id, peer_ip, peer_port in peers_to_connect:
            self._connect_to_peer(peer_id, peer_ip, peer_port)
    
    def _connect_to_peer(self, peer_id, peer_ip, peer_port):
        """
        Estabelece conexão com um peer específico.
        """
        with self.connections_lock:
            if peer_id in self.peer_connections:
                return  # Já conectado
        
        try:
            peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer_socket.settimeout(5)
            peer_socket.connect((peer_ip, peer_port))
            
            # Envia mensagem de registro
            payload = {
                "peer_id": self.peer_id,
                "blocks": list(self.block_manager.get_blocks())
            }
            message = Protocol.create_message(Protocol.REGISTER, payload)
            peer_socket.sendall(message)
            
            # Configura socket para receber resposta
            peer_file = peer_socket.makefile(mode='rb')
            
            # Espera pela resposta
            response_type, response_payload = Protocol.read_message_from_stream(peer_file)
            
            if response_type == Protocol.HAVE_BLOCKS:
                peer_blocks = set(response_payload.get("blocks", []))
                
                # Registra a conexão
                with self.connections_lock:
                    self.peer_connections[peer_id] = {
                        'socket': peer_socket,
                        'file': peer_file,
                        'addr': (peer_ip, peer_port),
                        'blocks': peer_blocks,
                        'last_activity': time.time()
                    }
                
                self.logger.info(f"Conexão estabelecida com peer {peer_id}")
                
                # Atualiza gerenciador de unchoke
                self.unchoke_manager.add_peer(peer_id, peer_blocks)
                
                # Inicia thread para processar mensagens desse peer
                peer_thread = threading.Thread(target=self._process_peer_messages, 
                                              args=(peer_id, peer_socket, peer_file))
                peer_thread.start()
                
                return True
            else:
                self.logger.warning(f"Resposta inesperada de {peer_id}: {response_type}")
                peer_socket.close()
                return False
                
        except Exception as e:
            self.logger.error(f"Erro ao conectar com peer {peer_id}: {str(e)}")
            return False
    
    def _request_block(self, peer_id, block_id):
        """
        Solicita um bloco específico a um peer.
        """
        with self.connections_lock:
            if peer_id not in self.peer_connections:
                return False
            
            peer_socket = self.peer_connections[peer_id]['socket']
            
        try:
            payload = {
                "block_id": block_id
            }
            message = Protocol.create_message(Protocol.REQUEST_BLOCK, payload)
            peer_socket.sendall(message)
            return True
            
        except Exception as e:
            self.logger.error(f"Erro ao solicitar bloco {block_id} do peer {peer_id}: {str(e)}")
            return False
    
    def _handle_block_request(self, peer_id, socket, block_id):
        """
        Processa solicitação de bloco de um peer.
        """
        if not self.block_manager.has_block(block_id):
            self.logger.warning(f"Peer {peer_id} solicitou bloco {block_id} que não possuímos")
            return
        
        try:
            # Obtém dados do bloco
            block_data = self.block_manager.get_block_data(block_id)
            
            # Envia dados do bloco
            payload = {
                "block_id": block_id,
                "data": block_data
            }
            message = Protocol.create_message(Protocol.BLOCK_DATA, payload)
            socket.sendall(message)
            
        except Exception as e:
            self.logger.error(f"Erro ao enviar bloco {block_id} para peer {peer_id}: {str(e)}")
    
    def _handle_block_data(self, peer_id, block_id, block_data):
        """
        Processa dados de bloco recebidos de um peer.
        """
        self.logger.info(f"Recebido bloco {block_id} do peer {peer_id}")
        
        # Armazena o bloco
        success = self.block_manager.add_block(block_id, block_data)
        
        if success:
            # Notifica peers sobre novo bloco
            self._notify_peers_about_new_block(block_id)
            
            # Registra que este peer foi útil (para tit-for-tat)
            self.unchoke_manager.register_block_received(peer_id)
    
    def _handle_have_blocks(self, peer_id, blocks):
        """
        Atualiza informação sobre blocos que um peer possui.
        """
        with self.connections_lock:
            if peer_id in self.peer_connections:
                self.peer_connections[peer_id]['blocks'] = blocks
        
        self.unchoke_manager.update_peer_blocks(peer_id, blocks)
    
    def _handle_unchoke(self, peer_id):
        """
        Processa notificação de unchoke de um peer.
        """
        self.unchoke_manager.set_peer_choked(peer_id, False)
    
    def _handle_choke(self, peer_id):
        """
        Processa notificação de choke de um peer.
        """
        self.unchoke_manager.set_peer_choked(peer_id, True)
    
    def _run_unchoke_process(self):
        """
        Thread que executa periodicamente o algoritmo de unchoke.
        """
        while self.running:
            try:
                # Executa lógica de unchoke
                self.unchoke_manager.run_unchoke_round()
                
                # Espera para próxima rodada
                time.sleep(10)  # 10 segundos entre rodadas
            except Exception as e:
                self.logger.error(f"Erro no processo de unchoke: {str(e)}")
                time.sleep(2)
    
    def _update_tracker_periodically(self):
        """
        Thread que atualiza o tracker periodicamente com os blocos possuídos.
        """
        while self.running:
            try:
                # Conecta ao tracker para atualizar
                tracker_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tracker_socket.connect(self.tracker_address)
                
                # Prepara mensagem com blocos atuais
                blocks = self.block_manager.get_blocks()
                payload = {
                    "peer_id": self.peer_id,
                    "ip": self.host,
                    "port": self.port,
                    "blocks": list(blocks)
                }
                
                # Envia atualização
                message = Protocol.create_message(Protocol.REGISTER, payload)
                tracker_socket.sendall(message)
                
                # Processa resposta mas não atualiza peers
                file = tracker_socket.makefile(mode='rb')
                Protocol.read_message_from_stream(file)
                tracker_socket.close()
                
                # Espera para próxima atualização
                time.sleep(30)  # 30 segundos entre atualizações
                
            except Exception as e:
                self.logger.error(f"Erro ao atualizar tracker: {str(e)}")
                time.sleep(10)
    
    def _notify_peers_about_new_block(self, block_id):
        """
        Notifica todos os peers conectados sobre um novo bloco adquirido.
        """
        with self.connections_lock:
            peers = list(self.peer_connections.items())
        
        for peer_id, connection in peers:
            try:
                payload = {
                    "blocks": list(self.block_manager.get_blocks())
                }
                message = Protocol.create_message(Protocol.HAVE_BLOCKS, payload)
                connection['socket'].sendall(message)
                
            except Exception as e:
                self.logger.error(f"Erro ao notificar peer {peer_id} sobre novo bloco: {str(e)}")