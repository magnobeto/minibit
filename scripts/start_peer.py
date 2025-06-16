# start_peer.py
import socket
import threading
import pickle
import time
import uuid
import logging

from peer.peer import Peer
from peer.block_manager import BlockManager

TRACKER_HOST = '127.0.0.1'
TRACKER_PORT = 8000
LISTEN_PORT = 0
REQUEST_INTERVAL = 10  # segundos

def register_with_tracker(peer_id, ip, port, blocks):
    msg = {
        'command': 'REGISTER',
        'peer_info': (peer_id, ip, port, blocks)
    }
    with socket.socket() as s:
        s.connect((TRACKER_HOST, TRACKER_PORT))
        s.sendall(pickle.dumps(msg))
        resp = pickle.loads(s.recv(8192))
    return resp.get('peers', [])

def request_peers(peer_id):
    msg = {'command': 'GET_PEERS', 'peer_id': peer_id}
    with socket.socket() as s:
        s.connect((TRACKER_HOST, TRACKER_PORT))
        s.sendall(pickle.dumps(msg))
        resp = pickle.loads(s.recv(8192))
    return resp.get('peers', [])

def update_blocks(peer_id, blocks):
    msg = {'command': 'UPDATE_BLOCKS', 'peer_id': peer_id, 'blocks': list(blocks)}
    with socket.socket() as s:
        s.connect((TRACKER_HOST, TRACKER_PORT))
        s.sendall(pickle.dumps(msg))
        return pickle.loads(s.recv(8192)).get('status') == 'ok'

def create_socket(port: int = 0) -> tuple[socket.socket, int]:
    """Creates and returns a configured socket and its port"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', port))
    sock.listen(5)
    return sock, sock.getsockname()[1]

def create_unique_socket() -> tuple[socket.socket, int]:
    """Creates a socket with a guaranteed unique port"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 0))
    sock.listen(5)  # Start listening immediately
    return sock, sock.getsockname()[1]


def handle_client(client_socket, block_manager):
    # Aqui você pode implementar a lógica de comunicação com o cliente
    try:
        data = client_socket.recv(1024)
        # Trate os dados recebidos conforme necessário
        # ...
    except Exception as e:
        print(f"Erro no cliente: {e}")
    finally:
        client_socket.close()

def start_peer():
    peer_id = str(uuid.uuid4())[:8]
    block_manager = BlockManager()
    
    server_socket, port = create_socket(LISTEN_PORT)
    print(f"[{peer_id}] Escutando em 127.0.0.1:{port}")

    peers = register_with_tracker(peer_id, '127.0.0.1', port, block_manager.blocks)
    print(f"[{peer_id}] Peers recebidos: {peers}")

    threading.Thread(target=lambda: accept_loop(server_socket, block_manager), daemon=True).start()
    threading.Thread(target=lambda: request_loop(peer_id, block_manager), daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando...")
        msg = {'command': 'REMOVE', 'peer_id': peer_id}
        with socket.socket() as s:
            s.connect((TRACKER_HOST, TRACKER_PORT))
            s.sendall(pickle.dumps(msg))
        server_socket.close()

def accept_loop(server_socket, block_manager):
    while True:
        client_socket, addr = server_socket.accept()
        threading.Thread(target=handle_client, args=(client_socket, block_manager), daemon=True).start()

def request_loop(peer_id, block_manager):
    while True:
        time.sleep(REQUEST_INTERVAL)
        peers = request_peers(peer_id)
        for pid, ip, port, their_blocks in peers:
            try:
                with socket.socket() as s:
                    s.connect((ip, port))
                    # Aqui você implementa a lógica de requisição de blocos diretamente pelo socket
                    # Por exemplo:
                    # s.sendall(b"GET_BLOCKS")
                    # resposta = s.recv(4096)
                    # processa a resposta e salva os blocos no block_manager
                    # update_blocks(peer_id, block_manager.blocks)
                    # Exemplo fictício:
                    # missing_blocks = block_manager.get_missing_blocks(their_blocks)
                    # for block_id in missing_blocks:
                    #     s.sendall(f"GET {block_id}".encode())
                    #     data = s.recv(4096)
                    #     block_manager.save_block(block_id, data)
                    update_blocks(peer_id, block_manager.blocks)
            except Exception as e:
                print(f"Erro ao conectar com {pid}@{ip}:{port} — {e}")

def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        block_manager = BlockManager()
        # Usa port=0 para atribuição automática (um inteiro)
        peer = Peer(port=0, block_manager=block_manager)
        peer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        peer.stop()
    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    start_peer()
    main()
