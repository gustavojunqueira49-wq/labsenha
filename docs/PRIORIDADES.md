# Prioridade de atendimento — leia antes de usar

> **Aviso.** A parametrização abaixo é uma **sugestão inicial** e **não constitui parecer jurídico**.
> A legislação muda e pode haver normas estaduais/municipais e regras internas. O hospital deve validar as
> categorias, a ordem e a fundamentação com sua assessoria jurídica/administrativa e mantê-las atualizadas
> em **Filas e prioridades › Categorias de prioridade**. Nada é fixo no código.

## O que é configurável
| Onde | O quê |
|---|---|
| Categorias de prioridade | Nome, descrição, **fundamentação legal**, **ordem** (1 = primeiro), ativo/inativo |
| Tipos de atendimento | Prefixo, cor, ordem, **nível de prioridade** (0 = fila comum), se exige categoria, ativo |
| Regras da fila (Configurações) | Máx. de prioritárias seguidas; tempo máx. de espera da fila comum |

## Como o sistema decide
Na recepção, o tipo **Prioritário** exige escolher a categoria (o funcionário confere o direito, p.ex. documento).
A senha sai como `P001`, guarda a categoria e a fila usa: nível do tipo → ordem da categoria → hora de chegada.
Para que a fila comum não fique indefinidamente parada, o administrador define:
* `queue.max_consecutive_priority` (ex.: 3): depois de 3 prioritárias seguidas, chama 1 comum.
  **0 = prioridade estrita.**
* `queue.aging_minutes` (ex.: 45): comum esperando mais que isso passa à frente. **0 = desligado.**

## Categorias carregadas como sugestão (verificar!)
Carregadas na instalação com o texto "SUGESTÃO INICIAL — validar…" no campo de fundamentação:
pessoa idosa 80+ (Estatuto da Pessoa Idosa, Lei 10.741/2003, art. 3º §2º), pessoa idosa 60+, pessoa com deficiência
(Lei 10.048/2000; Lei 13.146/2015), pessoa com TEA, gestante, lactante, pessoa com criança de colo, pessoa com
mobilidade reduzida, pessoa obesa (Lei 10.048/2000, com as alterações posteriores, entre elas a Lei 14.626/2023)
e "prioridade institucional".
Pontos que **exigem decisão do hospital**: a ordem entre categorias; o tratamento de "prioridade especial"
(80+) e de outras situações; e doadores de sangue — a Lei 14.626/2023 os prevê com prioridade **após todos os demais
beneficiados**, com comprovante; se quiser atendê-los, cadastre a categoria com a ordem adequada.
Consulte o texto vigente em https://www.planalto.gov.br/ (Lei 10.048/2000 e alterações) antes de validar.

Toda alteração nesses cadastros fica na **auditoria** (antes/depois, usuário, IP, data).
