# Agente de impressão

Programa pequeno (`agent.py`, só biblioteca padrão do Python) que fica no computador ligado à
impressora térmica USB e imprime as senhas geradas pelo servidor.

* Instalação no Windows: `scripts\install-agent.ps1` (ver `INSTALL.md`, seção 6).
* Teste rápido sem impressora: `mode = file` no `config.ini`; os bytes ESC/POS ficam em `spool/`.
* Diagnóstico: `python agent.py -v --once` e o arquivo `agent.log`.
* Nunca perde senha: a fila está no banco do servidor. Se a impressora falhar (sem papel/desligada) o
  agente avisa o servidor e a senha continua pendente até imprimir. Se a rede cair após imprimir, o agente
  lembra (`agent_state.json`) e não imprime em duplicidade quando a rede voltar.
* Impressora de REDE (cenário B) dispensa o agente: cadastre-a em *Impressão › Impressoras* como
  "Impressora de rede" e o próprio servidor envia por TCP 9100.
