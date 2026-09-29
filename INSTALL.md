# Instalação e colocação em produção

Tempo estimado: 1–2 h na primeira vez. Ordem: **1 servidor → 2 rede → 3 primeiro acesso → 4 cadastros →
5 impressão → 6 painel/TVs → 7 backup → 8 checklist**.

> Os scripts PowerShell (`.ps1`) e o serviço do Windows não puderam ser executados no ambiente de desenvolvimento
> (Linux). Execute-os em uma máquina de teste antes da produção e ajuste se necessário. O restante
> (backend, frontend, banco, agente, testes) foi validado, inclusive em PostgreSQL 16.

## 1. Servidor

### Requisitos
* PC/servidor dedicado, ligado 24 h no horário do laboratório (no-break recomendado), **IP fixo** (ex.: 192.168.1.100).
* Windows 10/11/Server 2016+ (ou Linux). 4 GB RAM são suficientes.
* [Python 3.11+](https://www.python.org/downloads/) — marque **"Add python.exe to PATH"**.
* [PostgreSQL 14+](https://www.postgresql.org/download/windows/) — anote a senha do usuário `postgres`.
  (Se a pasta `bin` do PostgreSQL não estiver no PATH, defina `PG_BIN_DIR` no `.env` — necessário para o backup.)
* Instale tudo **uma vez, com internet**; depois disso o sistema **não usa internet** (para instalar em máquina sem
  internet, faça `pip download -r backend/requirements.txt -d wheels` em outra máquina e use `pip install --no-index --find-links wheels`).

### Windows
```powershell
# PowerShell como Administrador, dentro da pasta do projeto
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -OpenFirewall
```
O script: cria o ambiente Python, instala dependências, gera `.env` (com senha aleatória do banco), cria usuário e
banco no PostgreSQL (pede a senha do `postgres`), aplica migrações, cria dados básicos e libera a porta no firewall.

Iniciar (teste): `.\scripts\start-server.ps1`.
Iniciar **automaticamente com o Windows**: `.\scripts\install-service.ps1` (Agendador de Tarefas, conta SYSTEM,
reinício automático se cair).

### Linux
```bash
./scripts/install.sh          # cria venv, .env, banco e migra
./scripts/start-server.sh     # ou use scripts/fila-senhas.service (systemd)
```

### Configuração manual do PostgreSQL (alternativa aos scripts)
1. `psql -U postgres -f database/init_db.sql` (edite a senha antes).
2. `copy .env.example .env` e ajuste `DATABASE_URL`.
3. `cd backend && .venv\Scripts\python -m app.cli migrate && .venv\Scripts\python -m app.cli seed`.

### `.env` — parâmetros principais
| Variável | Significado |
|---|---|
| `DATABASE_URL` | Conexão PostgreSQL (`postgresql+psycopg://usuario:senha@localhost:5432/senhas_lab`) |
| `PORT` | 80 → os PCs acessam `http://IP` (sem `:porta`). Use 8000 se a 80 estiver ocupada |
| `TIMEZONE` | Fuso do hospital (define "hoje" e horários) |
| `BACKUP_DIR` / `PG_BIN_DIR` | Pasta dos backups / pasta do `pg_dump` |
| `INITIAL_ADMIN_PASSWORD` | Vazio = senha aleatória em `data\PRIMEIRO_ACESSO.txt` |

## 2. Rede
1. Reserve/fixe o IP do servidor (no PC ou reserva no DHCP do roteador/switch).
2. Confirme, de outro PC, no navegador: `http://192.168.1.100` (deve abrir a tela de login) e
   `http://192.168.1.100/api/health` (deve responder `{"status":"ok"…}`).
3. Não abre? Firewall do servidor (porta `PORT`, redes Privada/Domínio) e se está na mesma rede/VLAN.
4. **Nome interno opcional:** `http://laboratorio` — crie um registro DNS no roteador/servidor DNS interno apontando
   para o IP, ou, sem DNS, adicione `192.168.1.100 laboratorio` ao arquivo `C:\Windows\System32\drivers\etc\hosts`
   de cada PC. O sistema funciona igual por IP ou nome.
5. Sem internet: nada a fazer — o sistema não faz nenhuma chamada externa (sem CDN, fontes ou APIs).

## 3. Primeiro acesso
1. Abra `http://IP-DO-SERVIDOR`, entre com `administrador` e a senha temporária de `data\PRIMEIRO_ACESSO.txt`.
2. O sistema **obriga trocar a senha**. Depois **apague** o arquivo `PRIMEIRO_ACESSO.txt`.
3. Esqueceu a senha do admin? No servidor: `cd backend && .venv\Scripts\python -m app.cli reset-admin`.

## 4. Cadastros (menu do administrador)
1. **Configurações:** nome do hospital/laboratório, mensagens, logo, som/voz, regras da fila, tempo de sessão, backup.
2. **Filas e prioridades:**
   * Tipos de atendimento (Normal, Prioritário, Agendado, Outros; "Urgência" vem inativo).
   * **Categorias de prioridade — valide com o jurídico (veja `docs/PRIORIDADES.md`).**
   * Guichês (COLETA 01…), computadores (nome + IP fixo) e painéis.
3. **Usuários:** um por pessoa (perfis: Recepção, Atendente, Painel, Supervisão, Administrador). Crie 1 usuário
   `painel` para cada TV. Ajuste permissões por perfil se necessário.
4. Dados de exemplo (treino): *Configurações › Carregar demonstração*; **antes da produção** use
   *Limpar dados de teste* (remove senhas, impressões e usuários demo).

## 5. Impressão

### Cenário A — impressora térmica USB no PC da recepção (com agente)
1. Instale o **driver** da impressora no Windows e imprima a página de teste do Windows.
   Anote o **nome exato** da impressora (Dispositivos e Impressoras).
2. No sistema: *Impressão › Agentes de impressão › Novo agente* → copie o **token** (aparece uma vez).
3. *Impressão › Impressoras › Nova*: conexão "USB/Windows via agente", escolha o agente, largura do papel
   (80 mm ≈ 42 colunas; 58 mm ≈ 32), tamanho da senha, margens, corte. Marque como padrão.
4. No PC da recepção, copie a pasta `print-agent` + `scripts\install-agent.ps1` e execute (Administrador):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\install-agent.ps1 -ServerUrl http://192.168.1.100 -Token pa_xxxxx -Printer "EPSON TM-T20"
   ```
   Instala o Python do agente, testa a conexão e registra a tarefa que inicia **com o Windows**.
5. Em *Impressão* confira **Agente ONLINE / Impressora ONLINE** e clique **TESTAR IMPRESSÃO**.
6. Acentos saindo errados? Mude a "Página de código" da impressora (cp850 → cp858/cp860/cp1252).

Teste sem impressora: em `print-agent\config.ini` use `mode = file` (grava os bytes em `spool\`).

### Cenário B — impressora de rede (sem agente)
Dê IP fixo à impressora (porta RAW/TCP **9100**), cadastre em *Impressão › Impressoras* como
"Impressora de rede" com IP/porta. O próprio servidor envia; o status é sondado a cada ~30 s.

### O que acontece se a impressora falhar
As senhas continuam sendo geradas; os jobs ficam na fila (tela *Impressão*) e saem quando a impressora/agente voltar.
"Reenviar" reprocessa jobs em ERRO; na recepção há "Reimprimir".

## 6. Painel de chamadas (TV/monitor)
1. Ligue o PC da TV à rede e abra no Chrome/Edge: `http://IP-DO-SERVIDOR/#/panel` com o usuário do perfil **PAINEL**
   (o login fica gravado no navegador e a sessão não expira).
2. Clique em **"Ativar som e tela cheia"** (os navegadores exigem um clique para liberar áudio). Para TV sem
   teclado/mouse use o modo quiosque que já libera o áudio:
   `chrome.exe --kiosk --autoplay-policy=no-user-gesture-required http://IP-DO-SERVIDOR/#/panel`
   (coloque um atalho em `shell:startup` para abrir junto com o Windows).
3. Voz: usa as vozes do Windows. Instale a voz **Português (Brasil)** em *Configurações › Hora e idioma › Fala*
   (funciona offline). Ajuste frase, velocidade e repetições em *Configurações › Áudio*.
4. O painel mostra **apenas senha e guichê**.

## 7. Backup
* Automático: a cada 24 h por padrão (Configurações › Backup); mantém os últimos 30. Manual: tela **Backup** ou `scripts\backup.ps1`.
* Configure o diretório para **outro disco** e copie periodicamente para outro equipamento/HD externo
  (backup no mesmo disco não protege contra falha do disco).
* Alerta: o dashboard avisa se o último backup passou de 36 h.
* **Restaurar:** tela Backup › Restaurar (cria antes um backup de segurança) ou `scripts\restore.ps1 -File <arquivo>` com o servidor parado.
  **Teste a restauração em outro computador antes de entrar em produção.**

## 8. Checklist de produção
- [ ] IP fixo no servidor; acesso `http://IP` OK nos PCs (recepção, guichês, TV, admin)
- [ ] Serviço do servidor e agente iniciam com o Windows (reinicie o PC e confira)
- [ ] Senha do admin trocada; `PRIMEIRO_ACESSO.txt` apagado; usuários nominais criados
- [ ] Categorias de prioridade e regras da fila **validadas pelo jurídico**
- [ ] Dados de demonstração removidos
- [ ] Impressão: TESTAR IMPRESSÃO OK; desligue a impressora e emita uma senha → volta a imprimir ao religar
- [ ] Painel em tela cheia com som e voz; chamada de teste OK
- [ ] Backup manual feito, arquivo copiado para outro equipamento, restauração testada
- [ ] Desconecte a internet do servidor e repita um fluxo completo (deve funcionar igual)
- [ ] No-break no servidor/switch; energia da impressora térmica

## 9. Atualizar o sistema
Pare o servidor, faça **backup**, substitua os arquivos do projeto (mantendo `.env`, `data`, `backups`), execute
`.\scripts\migrate.ps1` (`pip install -r backend\requirements.txt` se houver dependências novas) e inicie.
