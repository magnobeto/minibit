# start_peer.py
import socket
import threading
import pickle
import time
import uuid

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

def peer_worker(connection, addr, block_manager):
    peer = Peer(connection, block_manager)
    peer.start()

def start_peer():
    peer_id = str(uuid.uuid4())[:8]
    block_manager = BlockManager()
    
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(('127.0.0.1', LISTEN_PORT))
    listener.listen()
    ip, port = listener.getsockname()
    print(f"[{peer_id}] Escutando em {ip}:{port}")

    peers = register_with_tracker(peer_id, ip, port, block_manager.blocks)
    print(f"[{peer_id}] Peers recebidos: {peers}")

    threading.Thread(target=lambda: accept_loop(listener, block_manager), daemon=True).start()
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
        listener.close()

def accept_loop(listener, block_manager):
    while True:
        conn, addr = listener.accept()
        threading.Thread(target=peer_worker, args=(conn, addr, block_manager), daemon=True).start()

def request_loop(peer_id, block_manager):
    while True:
        time.sleep(REQUEST_INTERVAL)
        peers = request_peers(peer_id)
        for pid, ip, port, their_blocks in peers:
            try:
                with socket.socket() as s:
                    s.connect((ip, port))
                    peer = Peer(listen_port= s.getsockname()[1], tracker_address=(ip, port))
                    peer.request_missing_blocks()
                    update_blocks(peer_id, block_manager.blocks)
            except Exception as e:
                print(f"Erro ao conectar com {pid}@{ip}:{port} — {e}")

if __name__ == "__main__":
    start_peer()
