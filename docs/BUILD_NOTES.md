# Notas de build e testes reproduzíveis

Este documento é o registro canônico dos testes locais. Nenhum teste de build da porta foi executado por PokeUltrarecomp na auditoria inicial. Não preencher resultados por suposição.

## Regras

- Fixar commit completo de cada ferramenta e registrar o repositório de origem.
- Registrar versão exata de compilador, sistema operacional, SDK e dependências.
- Guardar logs completos localmente quando contiverem caminhos, hashes de entrada ou outras informações privadas; compartilhar somente uma cópia redigida.
- Não anexar ROMs, dumps, firmware, chaves, executáveis de jogo, recursos extraídos nem saídas derivadas.
- Se um teste exige entrada proprietária, mantê-la local e fora de Git/CI. Preferir casos sintéticos.
- Não classificar compilar uma ferramenta como prova de execução do jogo.
- Para cada falha, registrar comando, código de saída, etapa da falha e tentativa mínima de reprodução.
- Não registrar um teste como aprovado só porque o processo terminou sem crash; declarar a asserção que foi observada.

## Modelo de registro

Copie o modelo abaixo para uma issue ou nota nova ao executar um teste.

~~~text
Identificador do teste:
Data e hora:
Responsável:
Objetivo:
Repositório e commit completo:
Caminho/documentação de referência:
Sistema operacional e versão:
Windows build:
WSL/distribuição/kernel (se aplicável):
Arquitetura CPU:
Rust/C/C++/MSVC/MinGW version:
CMake/Ninja/Make/Python/Node versions:
Dependências e suas versões/commits:
Ferramentas instaladas e origem:
Entradas: sintéticas / próprias-localmente / nenhuma
Confirmação de que entradas e saídas proprietárias não foram publicadas:
Comando exato:
Diretório de trabalho:
Resultado esperado:
Resultado observado:
Código de saída:
Testes/asserções executados:
Log local (caminho privado):
Resumo público redigido:
Hashes de artefatos não proprietários (se relevante):
Erros ou advertências:
Tentativas de reprodução:
Classificação: PASS / FAIL / INCONCLUSIVE / NOT RUN
Critério de aceitação satisfeito:
Limitações:
Próximo passo:
~~~

## Primeiro registro: auditoria inicial

- Identificador: DOC-AUDIT-001
- Data: 2026-10-24
- Objetivo: inspecionar os repositórios de referência e preparar documentação do projeto.
- Ambiente local de compilação: não aplicável.
- Builds/testes de jogo: **não executados**.
- Resultado: leitura documental e verificação de caminhos públicos; os autores relatam resultados descritos em [AUDIT.md](AUDIT.md), mas eles não foram reproduzidos por este repositório.
- Limitações: estados e licenças podem mudar; commits de referência e os arquivos consultados devem ser revistos antes de qualquer incorporação.


## Teste de referência 001 — parser sintético de overrides

- Especificação e passos locais: [REFERENCE_TEST_001.md](REFERENCE_TEST_001.md).
- Runner: [tools/run_reference_test_001.ps1](../tools/run_reference_test_001.ps1); exige o argumento explícito AcceptThirdPartyCode antes de executar código de terceiros.
- Ferramenta de referência: 3dsrecomp, commit c3f21f94ba50d688025febc8974ff348d471b587.
- Comando: cargo test --locked --lib overrides::tests -- --nocapture.
- Ambiente esperado: Windows + PowerShell + Git + Rust/Cargo 1.88.0 ou mais recente.
- Entradas de jogo: nenhuma; fixtures de strings sintéticas.
- Execução nesta sessão: não realizada, porque rustc e cargo não estão instalados.
- Execução no computador do mantenedor: pendente.
- Estado: NOT RUN / NOT VERIFIED.
- Interpretação: PASS significa apenas que os testes do parser passaram no commit fixado. Não demonstra recompilação ARM nem execução de Ultra Sun/Ultra Moon.

O script busca apenas o commit fixado num diretório temporário, usa cache/build temporários e limpa esses dados ao terminar. O log resumido é escrito em %TEMP%; revise-o antes de compartilhar.

## Verificador local de segurança do repositório — 2026-10-24

- Arquivos: `tools/check_repository_safety.py` e `tests/test_repository_safety.py`.
- Dependências externas: nenhuma; usa a biblioteca padrão do Python e o Git.
- Testes unitários executados em ambiente temporário com fixtures sintéticas: **9 aprovados**. A suíte cobre caminhos proibidos, links locais e divergências entre o índice Git e a pasta de trabalho.
- Verificação sintática executada com `python -m py_compile`: aprovada.
- Foram exercitados dois cenários de integração sintéticos: índice sem links quebrados com pasta de trabalho modificada para conter um link quebrado; e índice com link quebrado enquanto a pasta de trabalho está corrigida. Ambos foram detectados na fonte correta.
- Teste de fumaça do comando CLI: aprovado num repositório Git temporário de exemplo, com documentos mínimos; uma fixture não rastreada com extensão `.3ds` também foi corretamente bloqueada.
- A verificação contra a árvore de trabalho completa da `main` ainda está pendente; os resultados acima não são um teste da porta do jogo.
- Escopo: detecta nomes/extensões/diretórios conhecidos de dados de jogo ou credenciais e links Markdown locais quebrados ou fora da raiz, tanto nos blobs do índice quanto nas versões atuais da pasta de trabalho e arquivos não ignorados não rastreados.
- Limitações: os nove testes e os cenários de integração foram executados numa área temporária, não contra toda a árvore da `main`. O verificador não examina histórico Git, arquivos ignorados que ainda não estão rastreados, conteúdo semântico arbitrário, licenças, direitos sobre dados ou compatibilidade do jogo. Um arquivo adicionado à força pode contornar regras de ignore; toda alteração ainda requer revisão de diff.
- Estado do runtime e teste de referência 001: continuam **NOT RUN / NOT VERIFIED**.

