# Ambiente uv padronizado (casa e CNPq)

Regra: **tudo é uv**, e o uv, o Python gerenciado e o cache ficam sempre em `E:\Programas\uv`, nos dois PCs.
Assim o `pyvenv.cfg` de cada `.venv` é igual nos dois lados, sem nome de usuário do Windows no caminho.

| Item | Caminho |
|---|---|
| uv | `E:\Programas\uv\bin\uv.exe` (no PATH do usuário) |
| Pythons gerenciados | `E:\Programas\uv\python` (`UV_PYTHON_INSTALL_DIR`) |
| Cache | `E:\Programas\uv\cache` (`UV_CACHE_DIR`) |
| Versão padrão | 3.14.8, fixada em cada projeto por `.python-version` (`3.14`); o `mesa` fica em 3.12 de propósito |

Cada projeto tem `pyproject.toml` + `uv.lock`, usa `uv sync --frozen` e referencia as bibliotecas próprias por
`[tool.uv.sources]` com caminho relativo e `editable = true` (ex.: `../../../Pessoais/acs_toolbox`).
Os `.venv` **não** são sincronizados (veja `sincronizacao/filtros.txt`): cada PC cria o seu.

## Padronizar um PC
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\ambiente\padronizar_uv_E.ps1" -SoVerificar   # só mostra
powershell -NoProfile -ExecutionPolicy Bypass -File "E:\Projetos\Pessoais\acs_toolbox\ambiente\padronizar_uv_E.ps1"               # aplica
```
Opções: `-PythonVersao 3.14.8`, `-SemVenvs` (só o uv e as variáveis). O script copia o uv para `E:\Programas\uv\bin`,
ajusta as variáveis de usuário e o PATH, instala o Python no `E:` e recria os `.venv` de `E:\Projetos` que ainda não
apontam para `E:\Programas\uv\python` (o antigo vai para `E:\_venvs_antigos`, e volta atrás se o `uv sync` falhar).
No fim imprime uma tabela OK/FALTA por projeto.
