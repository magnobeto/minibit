import socket
import threading
import json
import logging
import random
from typing import Dict, List, Tuple, Set

class Tracker:
    """
    Tracker central para o sistema MiniBit.
    - Registra peers e os arquivos que eles possuem.
    - Fornece a outros peers uma lista de quem tem os blocos de um arquivo.
    """
    def __init__(self, host='127.0.0.1', port=8000):
        self.host = host
        self.port = port
        # Estrutura: {file_name: {peer_id: (ip, port, {block_ids})}}
        self.files: Dict[str, Dict[str, Tuple[str, int, Set[str]]]] = {}
        self.lock = threading.Lock()
        self.server_socket = None
        self.running = False
        self.logger = logging.getLogger("Tracker")

    def start(self):
        """Inicia o servidor do tracker em uma nova thread."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        self.logger.info(f"Servidor iniciado em {self.host}:{self.port}")

        thread = threading.Thread(target=self._accept_connections, daemon=True)
        thread.start()
        # Permite que o programa principal continue para aguardar um KeyboardInterrupt
        while self.running:
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                self.stop()


    def _accept_connections(self):
        """Loop para aceitar novas conexões de peers."""
        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                self.logger.info(f"Nova conexão de {addr}")
                handler_thread = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                handler_thread.start()
            except OSError:
                # Ocorre quando o socket é fechado em self.stop()
                break
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erro ao aceitar conexões: {e}")

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]):
        """Processa mensagens de um peer conectado."""
        peer_id_for_session = None
        connection_alive = True
        try:
            with conn:
                while connection_alive:
                    # Lê o tamanho da mensagem (4 bytes)
                    raw_msglen = conn.recv(4)
                    if not raw_msglen:
                        break # Conexão fechada pelo cliente
                    msglen = int.from_bytes(raw_msglen, 'big')
                    
                    data = conn.recv(msglen)
                    if not data:
                        break # Conexão fechada pelo cliente
                    
                    message = json.loads(data.decode('utf-8'))
                    peer_id_for_session = message.get('peer_id')
                    
                    response = self._process_command(message)
                    
                    response_bytes = json.dumps(response).encode('utf-8')
                    conn.sendall(len(response_bytes).to_bytes(4, 'big') + response_bytes)
                    

                    connection_alive = False

        except (ConnectionResetError, BrokenPipeError, json.JSONDecodeError) as e:

            self.logger.warning(f"Conexão com {addr} (Peer: {peer_id_for_session}) perdida ou corrompida: {e}")
            if peer_id_for_session:
                self._remove_peer(peer_id_for_session)
        except Exception as e:
            self.logger.error(f"Erro ao lidar com o cliente {addr} (Peer: {peer_id_for_session}): {e}")
            if peer_id_for_session:
                self._remove_peer(peer_id_for_session)
        finally:

            self.logger.info(f"Comunicação com {addr} (Peer: {peer_id_for_session}) finalizada.")


    def _process_command(self, message: Dict) -> Dict:
        """Processa um comando recebido e retorna uma resposta."""
        command = message.get('command')
        peer_id = message.get('peer_id')
        
        with self.lock:
            if command == 'REGISTER':
                file_name = message['file_name']
                peer_addr = message['address']
                blocks = set(message['blocks'])
                
                if file_name not in self.files:
                    self.files[file_name] = {}
                
                self.files[file_name][peer_id] = (peer_addr[0], peer_addr[1], blocks)
                self.logger.info(f"Peer {peer_id} registrado para o arquivo '{file_name}' com {len(blocks)} blocos.")
                return {"status": "ok"}

            elif command == 'GET_PEERS':
                file_name = message['file_name']
                peers_list = []
                if file_name in self.files:
                    all_peers = self.files[file_name]
                    # Retorna todos os outros peers que têm o arquivo
                    other_peers = {pid: pinfo for pid, pinfo in all_peers.items() if pid != peer_id}
                    

                    if len(other_peers) < 5: # 
                        selected_peers = list(other_peers.items())
                    else:
                        selected_peers = random.sample(list(other_peers.items()), 5)

                    for pid, (ip, port, blocks) in selected_peers:
                        peers_list.append({"peer_id": pid, "address": (ip, port), "blocks": list(blocks)})
                
                self.logger.info(f"Enviando {len(peers_list)} peers para {peer_id} para o arquivo '{file_name}'.")
                return {"status": "ok", "peers": peers_list}

            elif command == 'UPDATE_BLOCKS':
                file_name = message['file_name']
                new_blocks = set(message['blocks'])
                if file_name in self.files and peer_id in self.files[file_name]:
                    ip, port, _ = self.files[file_name][peer_id]
                    self.files[file_name][peer_id] = (ip, port, new_blocks)
                    return {"status": "ok"}
                return {"status": "error", "message": "Peer or file not found"}

            else:
                return {"status": "error", "message": "Comando desconhecido"}

    def _remove_peer(self, peer_id_to_remove: str):
        """Remove um peer de todos os registros quando ele se desconecta com erro."""
        with self.lock:
            for file_name in self.files:
                if peer_id_to_remove in self.files[file_name]:
                    del self.files[file_name][peer_id_to_remove]
                    self.logger.info(f"Peer {peer_id_to_remove} removido (devido a erro/desconexão) do arquivo '{file_name}'.")

    def stop(self):
        """Para o servidor do tracker."""
        self.running = False
        if self.server_socket:
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((self.host, self.port))
            except ConnectionRefusedError:
                pass # Normal se o servidor já estiver parando
            self.server_socket.close()
        self.logger.info("Tracker parado.")
