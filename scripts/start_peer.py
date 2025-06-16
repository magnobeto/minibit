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

def run_peer(connection_info, block_manager):
    """
    Runs a peer instance
    Args:
        connection_info: Tuple of (host, port) or socket object
        block_manager: BlockManager instance
    """
    try:
        peer = Peer(connection_info, block_manager)
        peer.start()
    except Exception as e:
        print(f"Peer error: {e}")

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
        threading.Thread(target=run_peer, args=(client_socket, block_manager), daemon=True).start()

def request_loop(peer_id, block_manager):
    while True:
        time.sleep(REQUEST_INTERVAL)
        peers = request_peers(peer_id)
        for pid, ip, port, their_blocks in peers:
            try:
                with socket.socket() as s:
                    s.connect((ip, port))
                    peer = Peer(s)
                    peer.request_missing_blocks()
                    update_blocks(peer_id, block_manager.blocks)
            except Exception as e:
                print(f"Erro ao conectar com {pid}@{ip}:{port} — {e}")

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    try:
        # Create socket with unique port
        server_socket, port = create_unique_socket()
        logger.info(f"Created socket on port {port}")
        
        # Initialize peer with socket and port tuple
        block_manager = BlockManager()
        peer = Peer((server_socket, port), block_manager)
        
        # Start peer
        peer.start()
        
        # Keep alive until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            peer.stop()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    start_peer()
    main()
