# MiniBit: Sistema de Compartilhamento de Arquivos P2P

MiniBit é uma implementação simplificada em Python de um sistema de compartilhamento de arquivos cooperativo, inspirado nos princípios do BitTorrent. O projeto foi desenvolvido para a disciplina de Sistemas Distribuídos e foca nas estratégias de distribuição de blocos e na comunicação entre múltiplos peers.

## Funcionalidades Implementadas

- **Tracker Central**: Um servidor simples que coordena a descoberta de peers.
- **Divisão de Arquivos**: Arquivos são divididos em blocos de 16KB para compartilhamento.
- **Comunicação P2P**: Peers trocam blocos diretamente entre si, sem um servidor central de conteúdo.
- **Estratégia "Rarest First"**: Peers priorizam o download dos blocos menos comuns na rede, acelerando a distribuição geral.
- **Estratégia "Olho por Olho" (Simplificada)**: Cada peer periodicamente desbloqueia (unchokes) 4 peers "fixos" e 1 "otimista" para upload, com base no interesse e na dinâmica da rede.
- **Execução via Linha de Comando**: Uma interface simples para iniciar o tracker, um peer "seeder" (com o arquivo) ou peers "leechers" (para baixar).

## Como Executar

### Pré-requisitos

- Python 3.7 ou superior.

### 1. Preparar o Ambiente

Não há dependências externas. Basta ter o Python instalado.

### 2. Iniciar o Tracker

O tracker deve ser o primeiro a ser iniciado. Ele age como o ponto de encontro para os peers.

Abra um terminal e execute:

```bash
python main.py tracker
```
