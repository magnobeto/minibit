import socket
import threading
import pickle
from tracker.tracker import Tracker

tracker = Tracker()

HOST = '127.0.0.1'  # aceita conexões externas
PORT = 8000       # porta do tracker

def handle_client(conn, addr):
    print(f"[+] Nova conexão de {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break

            try:
                message = pickle.loads(data)
                command = message.get('command')

                if command == 'REGISTER':
                    peer_info = message.get('peer_info')
                    response = tracker.register_peer(tuple(peer_info))
                    conn.sendall(pickle.dumps({'status': 'ok', 'peers': response}))

                elif command == 'GET_PEERS':
                    peer_id = message.get('peer_id')
                    response = tracker.get_random_peers(peer_id)
                    conn.sendall(pickle.dumps({'status': 'ok', 'peers': response}))

                elif command == 'UPDATE_BLOCKS':
                    peer_id = message.get('peer_id')
                    blocks = set(message.get('blocks'))
                    updated = tracker.update_peer_blocks(peer_id, blocks)
                    conn.sendall(pickle.dumps({'status': 'ok' if updated else 'fail'}))

                elif command == 'REMOVE':
                    peer_id = message.get('peer_id')
                    removed = tracker.remove_peer(peer_id)
                    conn.sendall(pickle.dumps({'status': 'ok' if removed else 'fail'}))

                else:
                    conn.sendall(pickle.dumps({'status': 'error', 'message': 'Comando desconhecido'}))
            except Exception as e:
                conn.sendall(pickle.dumps({'status': 'error', 'message': str(e)}))
    finally:
        conn.close()
        print(f"[-] Conexão encerrada com {addr}")

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen()
        print(f"[Tracker] Servidor iniciado em {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()

if __name__ == "__main__":
    start_server()