# minibit
MiniBit: Implementação de um Sistema de Compartilhamento Cooperativo de Arquivos com Estratégias Distribuídas

📁 Estrutura de Diretórios

minibit/
├── tracker/
│   └── tracker.py
├── peer/
│   ├── peer.py
│   ├── block_manager.py
│   ├── peer_connection.py
│   └── unchoke_manager.py
├── common/
│   ├── protocol.py
│   └── utils.py
├── scripts/
│   ├── start_tracker.py
│   └── start_peer.py
├── data/
│   └── shared_file.txt
└── README.md