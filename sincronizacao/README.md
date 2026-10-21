# Sincronização de `E:\Projetos` entre o PC de casa e o PC do CNPq

> Pasta local (não versionada: está no `.gitignore` do acs_toolbox). Ela mesma é
> sincronizada, então os dois PCs sempre têm a versão atual dos scripts.

## Como funciona

```
PC do CNPq (E:\Projetos)  ⇄  Google Drive "Meu Drive/Projetos-sync"  ⇄  Notebook de casa (E:\Projetos)
                rclone bisync                                   rclone bisync
```

- **Ferramenta:** [rclone](https://rclone.org) `bisync`, que faz sincronização bidirecional. É um único
  `rclone.exe` em `%LOCALAPPDATA%\rclone\`. Não instala nada e não precisa de administrador.
- **Intermediário:** Google Drive da conta `albertodecamposesilva`, na pasta `Projetos-sync`.
  Os dados não são criptografados (decisão consciente: a conta é confiável).
- **Rede:** só HTTPS (porta 443) de saída, que o firewall do CNPq libera. Não há porta aberta em casa.
- **Quando:** sob demanda (ao chegar e antes de sair) ou agendado. Não é tempo real.
  Os dois PCs **não** precisam estar ligados ao mesmo tempo.
- **Mesmo caminho nos dois PCs:** tudo fica em `E:\Projetos`, então caminhos absolutos funcionam
  igual nos dois.

### Por que não as outras opções
| Opção | Motivo de não usar |
|---|---|
| Nextcloud do CNPq | Os administradores do órgão poderiam ler os projetos, e o serviço cai com frequência. |
| Google Drive para desktop | Não tem lista de ignore (sobe `.venv`, `node_modules`). Pastas fora do "Meu Drive" viram *backup por computador* e não sincronizam entre PCs. Lida mal com `.git`. |
| Syncthing | O firewall do CNPq só libera a porta 443, e os dois PCs precisariam estar ligados juntos (ou seria preciso uma VM paga). |
| Um git geral | Cada projeto já tem o seu git. Dados (PDF, CSV, JSONL) e arquivos fora do git também precisam ir. |

## Arquivos desta pasta

| Arquivo | Para quê |
|---|---|
| `sincronizar.cmd` | Atalho de duplo clique. Chama o `.ps1` e repassa os argumentos. |
| `sincronizar.ps1` | Executa o `rclone bisync` com as travas de segurança e grava o log. |
| `filtros.txt` | O que **não** sincroniza: `.venv`, `venv`, `node_modules`, `.next`, caches (inclusive os de perfis de Chrome), lixo do Windows/Office. |
| `instalar_rclone.ps1` | Baixa o rclone oficial, confere o SHA-256 e instala em `%LOCALAPPDATA%\rclone\`. |
| `preparar_git.ps1` | Para cada repositório com GitHub: commit do pendente, `pull --rebase` e `push`. Pula e marca REVISAR quando há possível segredo, arquivo com mais de 50 MB ou conflito. Repositórios sem remoto ficam com o rclone (vence o mais novo). `-SoListar` só mostra a situação. |
| `primeira_sincronizacao.ps1` | Faz tudo num PC novo ou defasado: instala o rclone, conecta o Drive, cria o marcador, roda `preparar_git.ps1`, `-Resync` e uma sincronização normal. |

Uma cópia desta pasta fica em `Meu Drive/Projetos-sync-instalador`, para o primeiro uso num PC que ainda
não tem os scripts. O notebook grava `Meu Drive/Projetos-sync-status/envio_inicial_concluido.txt` quando
o envio inicial termina, e o `primeira_sincronizacao.ps1` só prossegue se esse arquivo existir.

Fora desta pasta, em cada PC (nunca sincronizados):
- `%APPDATA%\rclone\rclone.conf`: credencial OAuth do Google Drive (remoto `gdrive`).
- `%LOCALAPPDATA%\rclone\bisync\`: estado do bisync (listagens da última execução).
- `%LOCALAPPDATA%\rclone\logs\`: logs de cada execução (ficam os últimos 60).

## O que é e o que não é sincronizado
- **Sincroniza:** todo o resto, inclusive `.git`, `.env`, `dist`, `.vscode` e os dados (PDF, CSV, JSONL...).
- **Não sincroniza:** veja `filtros.txt`. Inclui `Pessoais/Tarefas Diárias/mesa/dados/`, os dados vivos
  do `mesa` (WhatsApp, servidor, MCP), que **roda só no notebook de casa**. Não inicie o `mesa` no PC
  do CNPq com a mesma sessão do WhatsApp. Os ambientes virtuais são recriados em cada PC com
  `uv sync --directory "<projeto>"`, e o `node_modules` com `npm install`.
- Em 2026-10-20: cerca de 161 mil arquivos e 46 GB depois dos filtros.

## Configuração (uma vez por PC)

### 1. Garantir que `E:\Projetos` existe
- **Notebook de casa (`alberto-note`):** `E:` é uma unidade virtual persistente (registro
  `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\DOS Devices`, `E:` = `\??\C:\Disco_E`).
  `E:\Projetos` é uma **junção** para `C:\Projetos`:
  ```powershell
  New-Item -ItemType Junction -Path "C:\Disco_E\Projetos" -Target "C:\Projetos"
  ```
  Os dois caminhos funcionam. Prefira `E:\Projetos` em código e documentação.
- **PC do CNPq:** `E:` é o pendrive, e `E:\Projetos` é uma pasta real nele.

### 2. Instalar o rclone
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\instalar_rclone.ps1"
```
No PC do CNPq, antes da primeira sincronização, esta pasta ainda não existe lá. Copie-a de
`G:\Meu Drive\Projetos-sync\Pessoais\acs_toolbox\sincronizacao` (Google Drive para desktop) ou
baixe pela web do Drive para `E:\Projetos\Pessoais\acs_toolbox\sincronizacao`.

### 3. Conectar ao Google Drive
```powershell
& "$env:LOCALAPPDATA\rclone\rclone.exe" config create gdrive drive scope=drive
```
O navegador abre. Entre com `albertodecamposesilva` e autorize. Para testar:
```powershell
& "$env:LOCALAPPDATA\rclone\rclone.exe" lsd gdrive:Projetos-sync
```

### 4. Criar o marcador de segurança
```powershell
Set-Content "E:\Projetos\RCLONE_TEST" "Marcador do rclone bisync. Nao apagar." -Encoding ASCII
```
(Na primeira sincronização ele vai para o Drive e de lá para o outro PC.)

### 5. Primeira sincronização (`-Resync`)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\sincronizar.ps1" -Resync
```
- O `-Resync` **une** os dois lados e nunca apaga nada. Se um arquivo existe nos dois, fica o
  **mais novo**.
- **Primeiro PC (notebook):** envia tudo. São cerca de 46 GB e 161 mil arquivos. O Drive aceita poucos
  arquivos por segundo, então pode levar de 15 a 20 horas. Se for interrompido, rode `-Resync` de novo:
  ele continua de onde parou.
- **Segundo PC (CNPq):** baixa tudo e envia o que só existir lá.
- Para ver antes o que seria feito: acrescente `-DryRun`.

### Histórico da implantação (2026-10-20)
- Notebook: `preparar_git.ps1` fez commit e push em 6 repositórios com GitHub (Acordos de Cooperação
  FAPs, extratorlattes, Importações Diárias, VAR CNPq - RAG, VPN Connect, acs_toolbox). Os 8 sem remoto
  (Atualização das Páginas dos CAs, Faz Apresentações, Planilha Preliminar Automática, Planilhas Auxílio
  Julgamento, Preenche Planilha do Comitê Julgador, Pré-Seleção UNIVERSAL 2026, 500px, Tarefas Diárias)
  ficam com o rclone.
- Envio inicial a partir do notebook: cerca de 1 arquivo/s com o client_id compartilhado, daí a troca
  para client_id próprio.
- PC do CNPq: `E:\Projetos` já existia com versões defasadas. Use `primeira_sincronizacao.ps1`.

## Uso diário
- **Ao chegar em um PC:** sincronize (puxa o que mudou no outro).
- **Antes de sair:** sincronize (envia o que você mudou).
- Duplo clique em `E:\Projetos\Pessoais\acs_toolbox\sincronizacao\sincronizar.cmd`, ou:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\sincronizar.ps1"
  ```
- Sem mudanças, leva alguns minutos (só para listar os 161 mil arquivos).

### Agendar (opcional, sem admin)
A cada hora, enquanto o usuário estiver logado:
```powershell
$acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\sincronizar.ps1"'
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$config = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName "Sincronizar Projetos" -Action $acao -Trigger $gatilho -Settings $config
```
Para remover: `Unregister-ScheduledTask -TaskName "Sincronizar Projetos" -Confirm:$false`.

## Travas de segurança
1. **Pendrive caiu:** se `E:\Projetos` ou `E:\Projetos\RCLONE_TEST` não existir, o script aborta
   antes de chamar o rclone. Sem isso, o bisync entenderia "tudo foi apagado" e apagaria no Drive.
2. **`--check-access`:** nas execuções normais, o rclone também exige o `RCLONE_TEST` nos dois lados.
   No `-Resync` essa verificação fica desligada, porque na primeira vez o marcador ainda não existe no
   Drive. Nesse caso vale só a trava 1.
3. **Apagamento em massa:** o bisync aborta se mais de 50% dos arquivos fossem apagados. Se foi
   intencional, rode com `-Force`.
4. **Versões no Drive:** todo arquivo sobrescrito ou apagado no Drive vai antes para
   `Meu Drive/Projetos-sync-versoes/<data_hora>/`. A lixeira do Drive também guarda os apagados por
   30 dias. Limpe `Projetos-sync-versoes` de vez em quando.
5. **Conflito** (o mesmo arquivo alterado nos dois PCs entre sincronizações): vence o **mais novo**.
   O outro é mantido com o sufixo `.conflict1`, `.conflict2`... Procure por eles e resolva à mão:
   ```powershell
   Get-ChildItem "E:\Projetos" -Recurse -Force -Filter "*.conflict*" | Select-Object FullName
   ```
6. **Interrupção** (queda de rede, PC desligado no meio): `--resilient --recover` retomam na próxima
   execução. Uma trava de execução com mais de 2 h é considerada abandonada.

## Backup
Sincronizar não é fazer backup. Uma exclusão acidental, um arquivo corrompido ou um ransomware em um
PC chegam ao Drive e ao outro PC na sincronização seguinte. O backup versionado de `E:\Projetos` fica
no projeto `E:\Projetos\CNPq\importantes\Backup_DCTI`, no PC do CNPq. Até lá, as únicas proteções são
`Meu Drive/Projetos-sync-versoes` e a lixeira do Drive (30 dias).

## Cuidados
- **Não edite** arquivos em `G:\Meu Drive\Projetos-sync` (Drive para desktop) nem pela web: essa pasta
  é só do rclone. Trabalhe sempre em `E:\Projetos`.
- **Não trabalhe no mesmo repositório git nos dois PCs sem sincronizar no meio.** Arquivos internos do
  `.git` alterados dos dois lados geram conflitos difíceis de resolver. Se acontecer, prefira resolver
  com o próprio git (`git fetch`/`push` do GitHub).
- **Mudou `filtros.txt`?** Rode uma vez com `-Resync` em **cada** PC. O bisync recusa rodar quando os
  filtros mudam.
- **O bisync pediu `--resync`** (erro crítico no log)? Rode `-Resync`. É seguro, porque não apaga nada.
  Mas arquivos que você apagou de propósito desde a última sincronização podem voltar.
- **Pendrive do CNPq:** se o Windows parar de reconhecê-lo, nada se perde. É só reformatar ou trocar o
  pendrive, recriar `E:\Projetos` e o `RCLONE_TEST`, e rodar `-Resync`: tudo volta do Drive.

## Client ID próprio do Google Drive
O client_id compartilhado do rclone será desativado em 2026 e tem cota disputada. Use um client_id
próprio no projeto GCP `flowresolve`:
1. Ative a API: `gcloud services enable drive.googleapis.com --project flowresolve`.
2. No Console, abra **APIs e serviços → Tela de permissão OAuth**. Escolha o tipo *Externo* e
   **publique o app ("Em produção")**. Se ficar em *Teste*, o token expira a cada 7 dias.
3. Em **Credenciais → Criar credenciais → ID do cliente OAuth**, escolha o tipo *App para computador*.
4. Em cada PC, rode:
   `& "$env:LOCALAPPDATA\rclone\rclone.exe" config update gdrive client_id=<ID> client_secret=<SECRET>`
   e depois `& "$env:LOCALAPPDATA\rclone\rclone.exe" config reconnect gdrive:`. Na autorização, o
   Google avisa que o "app não é verificado": clique em *Avançado → Continuar*.

## Diagnóstico
```powershell
# Último log
Get-ChildItem "$env:LOCALAPPDATA\rclone\logs" | Sort-Object LastWriteTime | Select-Object -Last 1 | Get-Content -Tail 50
# Espaço usado no Drive
& "$env:LOCALAPPDATA\rclone\rclone.exe" size gdrive:Projetos-sync --fast-list
# Comparar os dois lados sem alterar nada
& "$env:LOCALAPPDATA\rclone\rclone.exe" check "E:\Projetos" gdrive:Projetos-sync --filter-from "E:\Projetos\Pessoais\acs_toolbox\sincronizacao\filtros.txt" --fast-list
```
