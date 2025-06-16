import argparse
import os
import sys
import time
import logging

# Adiciona o diretório raiz ao path para que possamos importar 'minibit'
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from minibit.tracker import Tracker
from minibit.peer import Peer

def main():
    """
    Ponto de entrada principal para iniciar o Tracker ou os Peers do MiniBit.
    Utiliza argparse para interpretar os comandos da linha de comando.
    """
    # Configuração básica de logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Parser principal
    parser = argparse.ArgumentParser(description="MiniBit: Um cliente P2P para compartilhamento de arquivos.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Comando para iniciar o Tracker
    parser_tracker = subparsers.add_parser("tracker", help="Inicia o servidor do Tracker.")
    parser_tracker.add_argument("--host", default="127.0.0.1", help="Host para o tracker (padrão: 127.0.0.1)")
    parser_tracker.add_argument("--port", type=int, default=8000, help="Porta para o tracker (padrão: 8000)")

    # Comando para iniciar um Peer
    parser_peer = subparsers.add_parser("peer", help="Inicia um cliente Peer.")
    parser_peer.add_argument("--tracker-addr", default="127.0.0.1:8000", help="Endereço do tracker no formato HOST:PORT (padrão: 127.0.0.1:8000)")
    parser_peer.add_argument("--file-path", help="Caminho para o arquivo a ser compartilhado (inicia como seeder).")
    parser_peer.add_argument("--file-name", help="Nome do arquivo para baixar (inicia como leecher).")

    args = parser.parse_args()

    if args.command == "tracker":
        # Inicia o Tracker
        tracker = Tracker(host=args.host, port=args.port)
        try:
            tracker.start()
        except KeyboardInterrupt:
            logging.info("Tracker encerrado pelo usuário.")
            tracker.stop()

    elif args.command == "peer":
        # Validação dos argumentos do Peer
        if not args.file_path and not args.file_name:
            print("Erro: Você precisa especificar --file-path (para ser seeder) ou --file-name (para ser leecher).")
            sys.exit(1)

        if args.file_path and not os.path.exists(args.file_path):
            print(f"Erro: O arquivo especificado em --file-path não foi encontrado: {args.file_path}")
            sys.exit(1)

        try:
            tracker_host, tracker_port_str = args.tracker_addr.split(':')
            tracker_port = int(tracker_port_str)
        except ValueError:
            print("Erro: O formato de --tracker-addr deve ser HOST:PORT (ex: 127.0.0.1:8000)")
            sys.exit(1)

        # Inicia o Peer
        peer = Peer(tracker_host=tracker_host, tracker_port=tracker_port)
        peer.start()

        # Configura o peer como seeder ou leecher
        if args.file_path:
            # Modo Seeder: compartilha um novo arquivo
            peer.share_file(args.file_path)
        else:
            # Modo Leecher: baixa um arquivo existente na rede
            peer.download_file(args.file_name)

        # Mantém o peer rodando
        try:
            while not peer.is_download_complete():
                time.sleep(2)
            
            # Se o download estiver completo, o peer agora é um seeder.
            # Ele continuará rodando para compartilhar com outros.
            logging.info(f"Peer {peer.peer_id} se tornou um seeder. Pressione Ctrl+C para sair.")
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logging.info(f"Peer {peer.peer_id} encerrado pelo usuário.")
        finally:
            peer.stop()

if __name__ == "__main__":
    main()