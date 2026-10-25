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

## Verificação remota de links internos — 2026-10-24

- Método: consultar documentos pela API do GitHub e verificar os destinos Markdown relativos contra arquivos publicados na branch `main`.
- Escopo: 14 documentos Markdown do projeto; 10 destinos locais únicos foram validados; nenhum link local quebrado foi encontrado nesse conjunto.
- Não foi usado GitHub Actions nem um clone completo do repositório.
- Limitação: esta é uma checagem documental remota, não a execução do script `tools/check_repository_safety.py` contra a árvore completa da `main`. Links externos foram identificados, mas não constituem uma auditoria de disponibilidade ou conteúdo.

## POC-001 — tradução ARM A32 sintética para C — 2026-10-24

- Especificação: [POC_001_SPEC.md](POC_001_SPEC.md).
- Código original: [tools/arm_subset_poc.py](../tools/arm_subset_poc.py); testes: [tests/test_arm_subset_poc.py](../tests/test_arm_subset_poc.py).
- Entrada: sequência sintética `E3A00003 E2800004 E12FFF1E`, correspondente ao subconjunto limitado `MOV r0,#3`, `ADD r0,r0,#4`, `BX LR`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0.
- Comandos executados: `python -m py_compile tools/arm_subset_poc.py tests/test_arm_subset_poc.py` e `python -m unittest discover -s tests -v`.
- Resultado observado: **11 testes aprovados**; compilação C11 temporária com `-Wall -Wextra -Werror` e execução do binário concluíram com código zero porque a função gerada retornou 7.
- Armazenamento: arquivo C e executável de teste foram criados dentro de diretório temporário e removidos ao final do teste; nenhum artefato de jogo foi usado.
- Classificação: **PASS para a demonstração sintética neste ambiente Linux**.
- Limites: não prova equivalência com instruções de jogo, não suporta Thumb, memória, desvios internos, flags, VFP/NEON, ABI do jogo nem serviços de 3DS; não foi executada no Windows. Não é uma porta nem um runtime de jogo.
- O teste de referência 001 e a execução do verificador contra a árvore completa da `main` continuam pendentes. O issue de procedência/escopo do `LICENSE` também continua aberto.

## Verificação remota de caminhos da árvore Git — 2026-10-24

- Fonte: árvore recursiva da branch `main` consultada pela API Git de leitura do GitHub; a resposta não estava truncada.
- Escopo: 22 arquivos rastreados; nenhum caminho correspondeu às extensões/nome de chave/diretórios proibidos listados pelo verificador local. A verificação é por nome e extensão, não por conteúdo.
- Links Markdown: 26 ocorrências de links internos foram conferidas em cinco documentos atualizados (README, POC-001, BUILD_NOTES, ROADMAP e CONTRIBUTING); nenhum destino interno quebrado foi encontrado.
- Limites: isto não executa o script Python no clone completo nem inspeciona o conteúdo binário/arbitrário, o histórico, os arquivos ignorados não rastreados ou a situação jurídica de arquivos. Não marca a revisão integral de segurança como concluída.

## POC-001 — iteração 2: SUB imediato — 2026-10-24

- Alteração: adicionado suporte limitado a `SUB` imediato (opcode A32 `0010`), mantendo o limite aos registradores `r0-r3`, condição AL e instruções sem atualização de flags.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E12FFF1E` — `MOV r0,#12`, `SUB r0,r0,#8`, `ADD r0,r0,#3`, `BX LR`; resultado esperado: 7.
- Testes adicionais: decodificação de SUB, rejeição de registrador de origem fora do subconjunto e verificação de C gerado para MOV/SUB/ADD.
- Verificação de conteúdo antes da execução: hashes de objeto Git dos arquivos em área temporária coincidiram com os blobs publicados nesta iteração: `tools/arm_subset_poc.py` = `07d3814e56c39cb200cce44158d59b76607c5d83`; `tests/test_arm_subset_poc.py` = `7ee6b241fabf7f1074eb43aabf6deb0c666c6c43`.
- Ambiente: Linux x86-64; Python 3.13.5; GCC 14.2.0.
- Comandos: `python3 -m py_compile tools/arm_subset_poc.py tests/test_arm_subset_poc.py`; `python3 -m unittest discover -s tests -v`.
- Resultado: **13 testes aprovados**; o teste host compilou o C emitido com `-std=c11 -Wall -Wextra -Werror`, executou o binário e confirmou o retorno 7 por código de saída zero.
- Classificação: **PASS para a demonstração sintética limitada no ambiente Linux**.
- Limites: nenhum ROM ou conteúdo de jogo foi aberto; não comprova equivalência com código de jogo, não cobre Thumb, flags, memória, fluxo de controle geral, ABI real, Windows ou serviços de 3DS. O teste de referência 001 continua pendente.

## Revalidação integral das suítes Python publicadas — 2026-10-24

- Método: os quatro arquivos listados abaixo foram obtidos da `main` e seus IDs de blob Git foram conferidos localmente com `git hash-object`; os testes foram executados em um diretório temporário isolado, sem um clone completo do repositório.
- Implementação POC: `tools/arm_subset_poc.py`, blob `07d3814e56c39cb200cce44158d59b76607c5d83`.
- Testes POC: `tests/test_arm_subset_poc.py`, blob `7ee6b241fabf7f1074eb43aabf6deb0c666c6c43`.
- Verificador de segurança: `tools/check_repository_safety.py`, blob `a372a3880723f5a17ae87cd81d4a41bd45d70edc`.
- Testes do verificador: `tests/test_repository_safety.py`, blob `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **22 testes aprovados, zero falhas e zero ignorados**. A POC foi compilada com C11, `-Wall -Wextra -Werror`, executada e confirmou o retorno 7. Os testes do verificador utilizaram repositórios Git sintéticos temporários para checar conteúdo preparado e pasta de trabalho divergentes.
- Classificação: **PASS para as duas suítes sintéticas Python e a compilação/execução host da POC no ambiente Linux descrito**.
- Limites: não executa o teste Rust de referência 001, não testa Windows, não verifica a árvore completa da `main` com o CLI do verificador e não prova equivalência, runtime ou gameplay. Nenhuma ROM ou recurso extraído foi usado.



## POC-001 — iteração 3: AND imediato e revalidação — 2026-10-24

- Alteração: adicionado suporte limitado a `AND` imediato, mantendo condição AL, registradores `r0-r3`, operação sem atualização de flags e limite de 256 palavras.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E2000007 E12FFF1E` — `MOV r0,#12`, `SUB r0,r0,#8`, `ADD r0,r0,#3`, `AND r0,r0,#7`, `BX LR`; resultado esperado: 7.
- Testes adicionais: decodificação de `AND`, rejeição de registrador de origem `r4`, verificação da emissão C do operador AND e atualização da fixture padrão.
- Os hashes de objeto Git dos quatro arquivos testados coincidem com os blobs publicados na `main`: `tools/arm_subset_poc.py` = `a4b7ee931829b317e6102060e848bdb61f90ded0`; `tests/test_arm_subset_poc.py` = `0001a5bbacace37eb305172b66983fe084ac43da`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **24 testes aprovados, zero falhas e zero ignorados** — 15 da POC e 9 do verificador de segurança. O C emitido foi compilado com C11 e `-Wall -Wextra -Werror`; o binário executou e confirmou retorno 7.
- Classificação: **PASS para as suítes sintéticas Python e prova nativa host no ambiente Linux descrito**.
- Limites: teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI do verificador não foi executado sobre uma cópia completa da `main`; nenhuma equivalência com jogo, runtime ou gameplay foi demonstrada. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.


## POC-001 — iteração 4: ORR imediato e revalidação — 2026-10-24

- Alteração: adicionado suporte restrito a `ORR` imediato, mantendo condição AL, registradores `r0-r3`, ausência de atualização de flags e limite de 256 palavras.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E2000007 E3800008 E12FFF1E` — `MOV r0,#12`, `SUB r0,r0,#8`, `ADD r0,r0,#3`, `AND r0,r0,#7`, `ORR r0,r0,#8`, `BX LR`; resultado esperado: 15.
- Testes adicionais: decodificação de `ORR`, rejeição de registrador de origem `r4`, emissão de ORR em C e teste host atualizado para confirmar o retorno 15.
- Os hashes de objeto Git dos quatro arquivos usados na execução coincidiram com os blobs da `main`: `tools/arm_subset_poc.py` = `4bc85756414e5b24c11ac09e181b1a430b40fd7c`; `tests/test_arm_subset_poc.py` = `60dde5f47da0a4b0069f43e0e1c7c65d5746f5b6`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **26 testes aprovados, zero falhas e zero ignorados** — 17 da POC e 9 do verificador de segurança. O C emitido foi compilado com C11 e `-Wall -Wextra -Werror`; o binário foi executado e confirmou retorno 15.
- Classificação: **PASS para as suítes sintéticas Python e prova nativa host no ambiente Linux descrito**.
- Limites: o teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI do verificador não foi executado sobre uma cópia completa da `main`; nenhuma equivalência com jogo, runtime ou gameplay foi demonstrada. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.


## POC-001 — iteração 5: EOR imediato e revalidação — 2026-10-24

- Alteração: adicionado suporte restrito a `EOR` imediato, com condição AL, registradores `r0-r3`, sem atualização de flags e limite de 256 palavras.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E2000007 E3800008 E2200001 E12FFF1E` — `MOV r0,#12`, `SUB r0,r0,#8`, `ADD r0,r0,#3`, `AND r0,r0,#7`, `ORR r0,r0,#8`, `EOR r0,r0,#1`, `BX LR`; resultado esperado: 14.
- Testes adicionais: decodificação de `EOR`, rejeição do registrador de origem `r4`, emissão do operador XOR em C e teste host atualizado para exigir retorno 14.
- Os hashes de objeto Git dos quatro arquivos usados na execução coincidem com os blobs publicados na `main`: `tools/arm_subset_poc.py` = `ad0421c3fe1b4c73979c5f03e3314f5f37220829`; `tests/test_arm_subset_poc.py` = `51f3719ffa2923ec2e9a90dbede0f3cc97b1c0db`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **28 testes aprovados, zero falhas e zero ignorados** — 19 da POC e 9 do verificador de segurança. O C emitido foi compilado com C11 e `-Wall -Wextra -Werror`; o executável rodou e confirmou retorno 14.
- Classificação: **PASS para as suítes sintéticas Python e prova nativa host no ambiente Linux descrito**.
- Limites: o teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI do verificador ainda não foi executado sobre uma cópia completa da `main`; nenhuma equivalência com jogo, runtime ou gameplay foi demonstrada. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.


## POC-001 — iteração 6: BIC imediato e revalidação — 2026-10-24

- Alteração: adicionado suporte restrito a `BIC` imediato, mantendo condição AL, registradores `r0-r3`, ausência de atualização de flags e limite de 256 palavras.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E2000007 E3800008 E2200001 E3C00002 E12FFF1E` — `MOV r0,#12`, `SUB r0,r0,#8`, `ADD r0,r0,#3`, `AND r0,r0,#7`, `ORR r0,r0,#8`, `EOR r0,r0,#1`, `BIC r0,r0,#2`, `BX LR`; resultado esperado: 12.
- Testes adicionais: decodificação de `BIC`, rejeição do registrador de origem `r4`, emissão de `rN & ~immediate` em C e teste host atualizado para exigir retorno 12.
- Os hashes de objeto Git dos quatro arquivos usados na execução coincidem com os blobs publicados na `main`: `tools/arm_subset_poc.py` = `5f9ef5ec05244c48a7b2d126520171b48f002330`; `tests/test_arm_subset_poc.py` = `5071f8cd6ac892e9278abe484d00c08fd4a96a46`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **30 testes aprovados, zero falhas e zero ignorados** — 21 da POC e 9 do verificador de segurança. O C emitido foi compilado com C11 e `-Wall -Wextra -Werror`; o executável rodou e confirmou retorno 12.
- Classificação: **PASS para as suítes sintéticas Python e prova nativa host no ambiente Linux descrito**.
- Limites: o teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI do verificador ainda não foi executado sobre uma cópia completa da `main`; nenhuma equivalência com jogo, runtime ou gameplay foi demonstrada. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.


## POC-001 — iteração 7: MVN imediato e pesquisa de fontes — 2026-10-24

- Alteração: adicionado suporte restrito a `MVN` imediato, com `S=0`, condição AL, registradores `r0-r3`, encoding canônico `Rn=0` e sem atualização de flags.
- Fixture sintética atual: `E3A0000C E2400008 E2800003 E2000007 E3800008 E2200001 E3C00002 E3E01000 E201000C E12FFF1E`. Depois das operações anteriores, `MVN r1,#0` produz `0xFFFFFFFF`, e `AND r0,r1,#12` assegura que a execução nativa retorna 12.
- Testes novos: decodificação de `MVN`, rejeição de encoding não canônico, emissão C do complemento e teste compilado/executado que falharia se o valor de `MVN` estivesse incorreto.
- Pesquisa: criado [CODEBASE_RESEARCH.md](CODEBASE_RESEARCH.md) com nove bases de código de ARM, emulação e recompilação, as funções técnicas e observações iniciais sobre licenças. A pesquisa é documental; nenhum código de terceiros foi copiado ou adicionado como dependência.
- Os hashes de objeto Git dos quatro arquivos usados na execução coincidem com os blobs publicados na `main`: `tools/arm_subset_poc.py` = `cd1f8bbc3bcace3142f933a327904def2de48c6e`; `tests/test_arm_subset_poc.py` = `41333a50933b8a6b18a5cdf2896295aad8c7714d`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **32 testes aprovados, zero falhas e zero ignorados** — 23 da POC e 9 do verificador de segurança. O C gerado foi compilado com C11 e `-Wall -Wextra -Werror`; o executável rodou e confirmou retorno 12.
- Classificação: **PASS para as suítes sintéticas Python e prova nativa host no ambiente Linux descrito**.
- Limites: CMN permanece pendente porque sua semântica atualiza NZCV e o POC ainda não modela esses flags. O teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI de segurança não foi executado sobre uma cópia completa da `main`; nenhuma equivalência com jogo, runtime ou gameplay foi demonstrada. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.


## Modelo isolado de flags NZCV — 2026-10-24

- Arquivos: `tools/arm_flags.py` e `tests/test_arm_flags.py`.
- Escopo: flags N/Z/C/V para soma/subtração uint32, carry-in/borrow-in, overflow assinado, nibble de flags e atualização de N/Z para resultados lógicos com preservação de V e preservação/substituição explícita de C.
- Separação intencional: o modelo ainda não está conectado à tradução ARM A32 → C e não habilita o bit S, CMN, CMP, TST ou saltos condicionais. Esses casos exigem definir o estado do CPSR/NZCV no código gerado e testes de execução/diferenciais antes de serem aceitos.
- Testes: **18 testes específicos aprovados** para o modelo; suíte completa **50 aprovados, zero falhas, zero ignorados** (23 da POC, 18 de NZCV e 9 de segurança).
- Blobs publicados e conferidos com hashes Git locais: `tools/arm_flags.py` = `0553247b268472b4385d7685f7770a7a95f09e16`; `tests/test_arm_flags.py` = `33071c2c71284dc0f2930e3e1e9ecd203bbfe09f`; `tools/arm_subset_poc.py` = `cd1f8bbc3bcace3142f933a327904def2de48c6e`; `tests/test_arm_subset_poc.py` = `41333a50933b8a6b18a5cdf2896295aad8c7714d`; `tools/check_repository_safety.py` = `a372a3880723f5a17ae87cd81d4a41bd45d70edc`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64, Python 3.13.5, GCC 14.2.0, Git 2.47.3.
- Comandos: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Limites: testes sintéticos independentes; nenhum código C do tradutor consome flags NZCV neste estágio, nenhuma ROM foi usada, Windows não foi testado e o teste de referência 001 permanece pendente.


## Integração de estado NZCV à POC-001 — 2026-10-24

- Alteração: o C emitido agora expõe `uint32_t synthetic_entry(uint8_t *nzcv_out)`; o chamador pode obter resultado em `r0` e o nibble `NZCV` (N no bit 3, Z no bit 2, C no bit 1, V no bit 0).
- Novas formas aceitas: `ADDS` e `SUBS` imediato atualizam N/Z/C/V; `CMN` imediato atualiza N/Z/C/V e não modifica o registrador de destino. Permanecem recusadas formas lógicas com bit S, `MOVS`/`MVNS`, e instruções condicionais; o CPSR completo e a semântica de shifter-carry ainda não foram integrados.
- Casos C compilados e executados: (1) MOV 0x80000000, SUB #1, ADDS #1 => resultado 0x80000000 e NZCV=0x9 (N=1,V=1); (2) MOV 0x80000000, SUBS #1 => resultado 0x7FFFFFFF e NZCV=0x3 (C=1,V=1); (3) mesma preparação com ADDS #1 seguida de CMN #0x80000000 => r0 permanece 0x80000000 e NZCV=0x7 (Z=1,C=1,V=1). O teste de CMN verifica que nenhum resultado é escrito em r0.
- Testes novos na suíte do tradutor: decodificação de ADDS, SUBS e CMN; rejeição de MOVS, CMN sem S e CMN com destino não canônico; testes de compilação/execução para ADDS, SUBS e CMN.
- Hashes de objeto Git dos arquivos testados conferem com os blobs publicados em `main`: `tools/arm_subset_poc.py` = `07a244db44aff366133fe9e2d060fc18a088d8f3`; `tests/test_arm_subset_poc.py` = `87cbee631cf812b3c82e70a73ca88d9163a1916d`; `tools/arm_flags.py` = `0553247b268472b4385d7685f7770a7a95f09e16`; `tests/test_arm_flags.py` = `33071c2c71284dc0f2930e3e1e9ecd203bbfe09f`; `tools/check_repository_safety.py` = `0319b53e8ed29209cc9bc7f958941bb4dc9e2bc8`; `tests/test_repository_safety.py` = `3bd44115751390dc6c613e758c94ef90f988eae2`.
- Ambiente: Linux 6.18.55 x86_64; Python 3.13.5; GCC 14.2.0; Git 2.47.3.
- Comandos executados: `python3 -m py_compile tools/*.py tests/*.py`; `python3 -m unittest discover -s tests -v`.
- Resultado observado: **58 testes aprovados, zero falhas e zero ignorados** — 31 do tradutor, 18 do módulo de referência NZCV e 9 do verificador de segurança. Os testes nativos foram compilados com C11, `-Wall -Wextra -Werror`, e executados em diretórios temporários.
- Limites: o teste de referência 001 continua `NOT RUN / NOT VERIFIED`; Windows não testado; o CLI do verificador não foi executado contra uma cópia completa da árvore de trabalho da `main`; não existe validação diferencial com um emulador independente nem equivalência com jogo/runtime. Nenhum conteúdo de jogo foi usado.

## Matriz diferencial sintética ARM — 2026-10-24

- Ferramenta nova: [tools/arm_differential_poc.py](../tools/arm_differential_poc.py), com testes em [tests/test_arm_differential_poc.py](../tests/test_arm_differential_poc.py). O verificador de segurança também exige os dois arquivos.
- Matriz: **72 fixtures** — 8 valores iniciais que cobrem zero, valores pequenos, limites de inteiro assinado e valores próximos de 2^32−1; 3 imediatos (1, 2 e 0x80000000); 3 operações (ADDS, SUBS, CMN). Cada operação é traduzida para C, compilada, executada e compara-se o retorno e o nibble NZCV com o módulo separado tools/arm_flags.py.
- Reproduzir: python tools/arm_differential_poc.py; testes específicos: python -m unittest discover -s tests -p "test_arm_differential_poc.py" -v. A execução completa da suíte é python -m unittest discover -s tests -v.
- Evidência preliminar: uma execução no workspace temporário retornou **72/72 correspondências** com /usr/bin/cc, C11, -Wall -Wextra -Werror, e os 3 testes específicos passaram. Contudo, essa execução não é aceita como validação da versão atual de main: os hashes locais de duas dependências não coincidiam com os blobs atuais do GitHub.
- Divergência de hashes observada ao revisar o workspace: tradutor local `tools/arm_subset_poc.py` = `be2fa0e7879c18d63fddcc8e7c644b2f9df7bc39`, enquanto o blob atual de main é `07a244db44aff366133fe9e2d060fc18a088d8f3`; modelo local `tools/arm_flags.py` = `d4b2f1b4b3256791353aabd5a56856b6821bd51a`, enquanto o blob atual de main é `0553247b268472b4385d7685f7770a7a95f09e16`. O código e o teste novos da matriz coincidem com os blobs de main, mas essa diferença nas dependências invalida a alegação de validação end-to-end da versão atual.
- Uma tentativa de executar toda a suíte nesse workspace incompleto resultou em 61 testes, com 2 falhas nos testes de CLI do tradutor e 59 aprovados. Como os arquivos locais do tradutor/modelo não correspondem aos blobs atuais de main, isso não é evidência de falha da versão publicada nem de sucesso da suíte integral atual. Repetir em um checkout sincronizado permanece pendente.
- Limite importante: esta é uma comparação entre o C emitido e o modelo de flags separado **dentro deste projeto**, não uma comparação com um emulador independente. Não valida ROM, runtime ou gameplay. A suíte integral combinada deve ser repetida num checkout limpo da main; Windows e o teste de referência 001 continuam pendentes.

## POC-001 — iteração 8: CMP imediato e validação sincronizada — 2026-10-24

- Nova instrução: \`CMP\` imediato sob limites explícitos — condição AL, \`Rn\` em \`r0-r3\`, \`S=1\` e encoding canônico \`Rd=0\`. O tradutor calcula as flags N/Z/C/V pela subtração, mas não grava o resultado em qualquer registrador. Formas sem S ou com destino não canônico são rejeitadas.
- Teste nativo principal: \`E3A00102 E3500001 E12FFF1E\` (\`MOV r0,#0x80000000\`; \`CMP r0,#1\`; \`BX LR\`) retorna \`r0 = 0x80000000\` e \`NZCV = 0x3\`, confirmando C=1 e V=1 sem sobrescrever o valor comparado.
- Matriz ampliada: **96 fixtures** (8 valores iniciais × 3 imediatos × 4 operações: \`ADDS\`, \`SUBS\`, \`CMN\`, \`CMP\`). O executável C retornou valores e NZCV esperados para **96/96 casos**, comparados ao modelo separado \`tools/arm_flags.py\`. Compilador \`/usr/bin/cc\`, C11, \`-Wall -Wextra -Werror\`.
- Suíte: **67 testes aprovados, zero falhas, zero ignorados** — 36 do tradutor, 18 do modelo NZCV, 9 do verificador de segurança e 4 da matriz diferencial. Comandos: \`python3 -m py_compile tools/*.py tests/*.py\`; \`python3 tools/arm_differential_poc.py\`; \`python3 -m unittest discover -s tests -v\`.
- O resultado anterior de 61 testes em arquivos temporários desatualizados e a matriz preliminar de 72 casos ficam supersedidos por esta execução. Os oito arquivos Python usados foram comparados por hash Git com os blobs de \`main\`: \`tools/arm_subset_poc.py\` = \`640b1a1e224e79bc47a234a573ccd9c639587151\`; \`tests/test_arm_subset_poc.py\` = \`3d177f3506b4c7393debe1d9d4ee5a6bdf7b75f4\`; \`tools/arm_flags.py\` = \`0553247b268472b4385d7685f7770a7a95f09e16\`; \`tests/test_arm_flags.py\` = \`33071c2c71284dc0f2930e3e1e9ecd203bbfe09f\`; \`tools/check_repository_safety.py\` = \`b7401626a83ef844920e7a81b4269f3be42bbc4d\`; \`tests/test_repository_safety.py\` = \`3bd44115751390dc6c613e758c94ef90f988eae2\`; \`tools/arm_differential_poc.py\` = \`947b477c176842e8f1bdc06ac678491c16aeccb6\`; \`tests/test_arm_differential_poc.py\` = \`82ee5529ffaf125db4d9803fc24480e02561f9e1\`.
- Limites: a comparação é interna ao projeto, não usa emulador e não comprova equivalência com o hardware ou com o jogo. O clone integral da árvore não pôde ser obtido neste ambiente por falha de resolução DNS; a validação se baseia no conjunto Python cujos blobs foram verificados. O teste de referência 001 continua \`NOT RUN / NOT VERIFIED\`, Windows não foi testado e a pendência de procedência/escopo de \`LICENSE\` continua aberta.

## POC-001 — iteração 9: B, BEQ e BNE — 2026-10-24

- Adicionado suporte limitado a saltos ARM A32 \`B\` (AL), \`BEQ\` e \`BNE\`. O decodificador rejeita \`BL\` e condições de salto fora do subconjunto. O offset de 24 bits é interpretado como signed e o destino usa o PC de A32 (instrução atual + 2 palavras de fixture); qualquer destino fora da sequência é recusado antes de emitir C.
- O código C gerado usa \`goto\` para rótulos dos destinos validados; apenas rótulos referenciados são emitidos, para manter a compilação limpa com \`-Wall -Wextra -Werror\`. \`BEQ\` testa Z=1, \`BNE\` testa Z=0, e saltos não alteram NZCV.
- Testes nativos: salto AL que ignora uma instrução; \`BEQ\` tomado após \`CMP\` igual; \`BNE\` tomado após comparação desigual; \`BNE\` não tomado quando Z=1; rejeição de destino fora da fixture, \`BL\` e condição não suportada. A primeira execução dos novos casos expôs rótulos C não usados; a geração foi corrigida e todos os testes passaram depois da correção.
- Validação executada em \`/tmp/pokeultra-review\`, com as versões Python conferidas por hash Git com os blobs de \`main\`: \`python3 -m py_compile tools/*.py tests/*.py\` passou; \`python3 tools/arm_differential_poc.py\` passou com **96/96** casos; \`python3 -m unittest discover -s tests -v\` passou com **74 testes, zero falhas e zero ignorados**. Contagem: 43 testes do tradutor, 18 do modelo NZCV, 9 do verificador de segurança e 4 da matriz diferencial. O compilador disponível foi \`/usr/bin/cc\`, usando C11, \`-Wall -Wextra -Werror\`.
- Blobs de implementação/testes conferidos: \`tools/arm_subset_poc.py\` = \`6b4f263a5de9a9199a3a137e0879f66df38f91b2\`; \`tests/test_arm_subset_poc.py\` = \`810be864cdcc913b7eff70f592a21899ba764d7b\`; \`tools/arm_flags.py\` = \`0553247b268472b4385d7685f7770a7a95f09e16\`; \`tests/test_arm_flags.py\` = \`33071c2c71284dc0f2930e3e1e9ecd203bbfe09f\`; \`tools/check_repository_safety.py\` = \`b7401626a83ef844920e7a81b4269f3be42bbc4d\`; \`tests/test_repository_safety.py\` = \`3bd44115751390dc6c613e758c94ef90f988eae2\`; \`tools/arm_differential_poc.py\` = \`947b477c176842e8f1bdc06ac678491c16aeccb6\`; \`tests/test_arm_differential_poc.py\` = \`82ee5529ffaf125db4d9803fc24480e02561f9e1\`.
- Limites: o experimento segue sendo um tradutor sintético, não é runtime do jogo nem teste de Pokémon. Não há laços de execução validados de propósito (um loop infinito poderia não terminar); as fixtures precisam ter retorno finito. Não há suporte a BL, endereços de memória, chamadas entre funções, condições além de EQ/NE, predicação genérica, Thumb ou CPSR completo. Esta rodada não usa emulador. Windows e o teste de referência 001 permanecem pendentes; a decisão sobre a procedência/escopo do \`LICENSE\` também continua aberta.

## POC-001 — iteração 10: rejeição de loops não verificados — 2026-10-24

- Restrição adicional: destinos de saltos precisam ser posteriores à instrução atual. Saltos para trás e para a própria instrução são rejeitados para impedir loops ilimitados em fixtures nativas nesta fase; o suporte a laços fica adiado até existir um orçamento de execução explícito e testes de término.
- Teste negativo novo: \`B\` com offset \`-2\`, que apontaria para a própria instrução, tem de falhar com \`UnsupportedInstruction\`. Isso é adicional ao teste que rejeita destinos fora da sequência.
- Revalidação local depois da mudança: \`python3 -m py_compile tools/*.py tests/*.py\` aprovado; matriz diferencial \`python3 tools/arm_differential_poc.py\` — **96/96**; suíte completa \`python3 -m unittest discover -s tests -v\` — **75 testes aprovados, zero falhas e zero ignorados**. Contagem: 44 do tradutor, 18 de NZCV, 9 de segurança e 4 da matriz diferencial. C11 com \`/usr/bin/cc\`, \`-Wall -Wextra -Werror\`.
- Hashes dos arquivos alterados, comparados com os blobs de \`main\`: \`tools/arm_subset_poc.py\` = \`1c7562296300e75d445af612f0a9a7d402e3bd6b\`; \`tests/test_arm_subset_poc.py\` = \`3031e8a0757fb70d49c37214c80295ce32482a91\`. A suíte usou versões Python sincronizadas e conferidas pelos hashes publicados do projeto.
- Limites na iteração 10 (registro histórico, antes da ampliação dos códigos de condição): só \`B\`, \`BEQ\` e \`BNE\` para frente, com alvos dentro da fixture. A iteração 11 amplia a tabela de condições para EQ..LE e adiciona predicação de dados. Nenhum emulador foi usado. Não há recompilador geral nem runtime de Ultra Sun/Ultra Moon; o teste de referência 001, Windows e a decisão sobre a procedência/escopo do \`LICENSE\` permanecem pendentes.

## POC-001 — iteração 11: execução condicional de instruções de dados — 2026-10-24

- Alteração: os opcodes de dados imediatos já suportados aceitam condições A32 EQ..LE (condições 0x0 a 0xD) e são representados como tuplas predicadas. AL (0xE) mantém a forma original; o campo 0xF continua rejeitado. A condição é convertida para um if no C gerado. Se a condição for falsa, o bloco não escreve em registradores nem altera NZCV.
- A mesma tabela de condições usada para gerar desvios também é usada para a predicação das operações. A suíte agora gera casos para todas as 14 condições e os 16 nibbles de NZCV para dois comportamentos diferentes: desvio condicional e instrução de dados condicionada, totalizando 448 funções nativas nessa matriz. A comparação usa a tabela booleana independente já presente no teste.
- Teste específico adicionado para ADDEQS r0,r0,#1: com Z=0, a instrução é ignorada e o estado NZCV de entrada deve ser preservado; com Z=1, ela executa e atualiza r0 e NZCV. Também é testado que o campo de condição 0xF de uma instrução de dados seja recusado.
- Arquivos alterados: tools/arm_subset_poc.py e tests/test_arm_subset_poc.py; documentação atualizada em docs/POC_001_SPEC.md, README.md e docs/ROADMAP.md.
- Blobs atuais verificados no GitHub: \`tools/arm_subset_poc.py\` = \`8ca13e7d9fd3e174ce0abedf55b541132a15b90a\`; \`tests/test_arm_subset_poc.py\` = \`39eddf42eef5929ca83c7447ffb0d61f1fc98d80\`; \`docs/POC_001_SPEC.md\` = \`7f43efa6b2795ebb1c82cf3d1aa45141e9c73378\`; \`README.md\` = \`c7b0d56ffe97aff6b3ad48df154f1ba9f6d19413\`; \`docs/ROADMAP.md\` = \`bd08d9d8d0e3c01630cc95e69d3bd520d3de348b\`.
- **Estado de validação desta iteração: PENDENTE.** A última suíte integral documentada antes da predicação tinha 85 testes aprovados. A predicação adicionou dois testes e a continuação adicionou um teste nativo para `CMP` condicional, totalizando **88 testes esperados** (57 tradutor + 18 modelo NZCV + 9 verificador de segurança + 4 matriz diferencial), e amplia o teste nativo de condições. Não consegui executar a suíte desta versão nesta sessão: git clone https://github.com/CarlosCosta07-s/PokeUltrarecomp.git falhou porque o ambiente não conseguiu resolver github.com. Não afirmo que os novos testes passaram. Executar python3 -B -m unittest discover -s tests -v e python3 tools/arm_differential_poc.py num checkout sincronizado é o próximo critério de aceitação.
- Limites: predicação só é suportada para instruções dentro do subconjunto explícito; BL, condição 0xF, memória, Thumb, formas lógicas com S-bit e carry do shifter permanecem fora do escopo. Saltos para trás seguem bloqueados para não permitir loops sem orçamento de execução. Nenhum emulador foi usado; não existe equivalência com gameplay nem runtime próprio concluído.


## POC-001 — continuação: flags de CMP condicional — 2026-10-24

- Adicionado `test_predicated_cmp_preserves_or_updates_flags_according_to_condition`, com duas funções C compiladas e executadas: `CMPEQ r0,#0` com Z=0 deve preservar NZCV=0x8; `CMPNE r0,#0` com o mesmo estado deve produzir NZCV=0x6.
- O teste usa C11 com `-Wall -Wextra -Werror`, seguindo o padrão dos testes nativos existentes.
- Blob atual de `tools/arm_subset_poc.py`: `8ca13e7d9fd3e174ce0abedf55b541132a15b90a`. Blob atual de `tests/test_arm_subset_poc.py`: `ada971f479a4d8371d0ae86a4fd6c72e61340335`.
- Validação pendente: o teste foi adicionado ao repositório, mas não foi executado nesta sessão. A suíte agora tem 88 testes esperados (57 do tradutor, 18 do modelo NZCV, 9 do verificador de segurança e 4 da matriz diferencial). Não declarar sucesso antes de executar num checkout atualizado.

## Verificação nativa isolada complementar — 2026-10-24

A tentativa de clonar o repositório inteiro continua bloqueada por falha de resolução DNS. Para não confundir esse bloqueio com ausência total de validação, extraí a fonte atual de `tools/arm_subset_poc.py` por meio da integração GitHub e confirmei seu Git blob SHA-1 (`8ca13e7d9fd3e174ce0abedf55b541132a15b90a`) antes da execução num diretório temporário isolado, com Python 3.13.5 e `cc` (GCC).

- **Fixture padrão:** o C gerado compilou com C11, `-Wall -Wextra -Werror`; o executável retornou código zero ao verificar resultado 12 e NZCV 0.
- **Matriz independente de condições:** 448 verificações (14 condições × 16 estados NZCV × desvio/predicação) compilaram e executaram sem divergências contra uma tabela booleana independente.
- **Predicação de comparação e aritmética:** os harnesses nativos de `CMP` condicional e `ADDS` condicional passaram; flags preservadas quando a condição falha e atualizadas quando a condição passa.
- **Proteção de fluxo:** o tradutor continuou recusando desvio para trás/autoalvo.

Esta verificação isolada **não é a suíte integral do repositório** e não substitui `python -m unittest discover -s tests -v`: os 88 testes esperados (57 do tradutor, 18 do modelo NZCV, 9 do verificador de segurança e 4 da matriz diferencial) continuam pendentes de execução num checkout completo e sincronizado. Também não valida o runtime do jogo, uma ROM, nem compatibilidade com Ultra Sun/Ultra Moon.

## POC-001 — laços limitados por orçamento de execução — 2026-10-24

- Implementado `max_execution_steps` em `translate` e `--max-execution-steps` na CLI, com intervalo validado de 1 a 100.000 e rejeição de bools/valores fora da faixa.
- A API antiga e a assinatura `synthetic_entry(uint8_t *nzcv_out)` permanecem iguais quando o orçamento é omitido; nesse modo, desvio para trás/autoalvo continua rejeitado. Quando o orçamento é fornecido, o C usa a assinatura `synthetic_entry_bounded(nzcv_out, steps_executed_out, execution_status_out)`.
- Cada instrução visitada conta, incluindo instruções predicadas que não executam o corpo e `BX LR`. `execution_status_out=0` significa retorno normal; `=1` significa esgotamento do limite. O estado de registradores/NZCV no esgotamento é parcial, não um retorno normal.
- Foram adicionados quatro testes à suíte do tradutor: laço que termina dentro de 8 passos, orçamento esgotado após 2 passos, validação de limites/opção CLI e um caso em que uma instrução predicada falsa ainda consome um passo. A suíte do tradutor passa a ter 61 métodos; o total combinado esperado é 92 (61 + 18 + 9 + 4).
- **Validação isolada:** `python -m unittest discover -s tests -v` executou os 61 testes do tradutor no workspace temporário, em 4,841 s: **61 aprovados, zero falhas e zero ignorados**. `cc`/GCC compilou e executou os harnesses nativos com C11, `-Wall -Wextra -Werror`, incluindo a matriz de 448 combinações e o novo laço. O blob Git da fonte local corresponde exatamente ao `main` (`2e77aea8fb39d899f8f58f5b6e58b914956aadb4`).
- **Limitação de validação:** os testes foram executados isoladamente, com uma cópia local dos testes de tradutor baseada no arquivo publicado, e não em checkout integral recém-clonado. A suíte combinada de 92 testes, o verificador contra toda a árvore e o teste de referência 001 continuam pendentes; clone continua bloqueado por DNS. Não afirmar compatibilidade com jogo nem runtime próprio concluído.

## Execução integral da suíte e correção detectada — 2026-10-25

- Adicionado `.github/workflows/poc-001-tests.yml` para fazer checkout da árvore completa da `main` e executar verificação sintática, matriz diferencial, suíte unitária combinada e verificador de segurança. O workflow roda nas alterações relevantes em `main` e pode ser iniciado manualmente; ele não é necessário para executar a POC localmente.
- **Primeira execução:** [run 40155883742](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40155883742) falhou num teste: a renomeação das funções geradas em `test_predicated_cmp_preserves_or_updates_flags_according_to_condition` removia acidentalmente `uint32_t`, causando erro de compilação C com `-Werror`. Os outros 91 testes não falharam; a suíte integral terminou com exatamente uma falha.
- **Correção:** commit `e1a29126c68324853e73da7dd2b16657566e41c2`, que preserva `uint32_t` nos dois nomes de função do teste `CMP` condicional.
- **Execução seguinte aprovada:** [run 40155966816](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40155966816), no commit `e1a29126c68324853e73da7dd2b16657566e41c2`. Ambiente reportado: Python 3.14.4, GCC 15.2.0, runner Ubuntu. Resultado: `Ran 92 tests in 1.428s`, `OK`; sintaxe Python aprovada; matriz diferencial `96/96` aprovada; `tools/check_repository_safety.py` retornou `PASS`, verificando 28 caminhos indexados e zero arquivos não ignorados não rastreados.
- O checkout hospedado foi integral, portanto a suíte foi testada unida, no mesmo commit, e não apenas como arquivos isolados. A resolução DNS no ambiente local ainda falha; isso não impediu a validação remota da árvore completa. Nenhum emulador, ROM, dump, firmware ou chave foi usado.
- **Escopo do resultado:** demonstra a consistência atual da POC sintética e dos testes do repositório, não um runtime de jogo, compatibilidade de Pokémon, Windows ou cobertura de gameplay. O teste de referência 001 e a decisão sobre procedência/abrangência do arquivo `LICENSE` preexistente permanecem pendentes.`

## Primeiro fluxo específico dos jogos — intake local e candidatos de revisão — 2026-10-25

- Adicionados perfis `targets/pokemon_ultra_sun.json` e `targets/pokemon_ultra_moon.json` para separar os alvos e identificar IDs-base/atualização conhecidos. Esses IDs e perfis não contêm código dos jogos.
- Adicionado `tools/inspect_3ds_target.py`, que aceita um ExHeader e o arquivo ExeFS `.code` já descomprimido, fornecidos por caminho local. Lê os campos SCI, extrai tamanho de stack/BSS e metadados de `.text`, `.rodata`, `.data`, verifica tamanhos/páginas, regiões virtuais sobrepostas, compatibilidade grosseira de tamanho e o ID de título opcional. Calcula SHA-256 mas não copia bytes nem inclui caminho absoluto no relatório.
- Os perfis contêm candidatos de tamanho reportados por uma referência comunitária: 5.914.624 bytes para um candidato `base-v1.0` e 5.922.816 bytes para um candidato `update-v1.2`. O programa devolve `candidate-by-size-only`, nunca `verified_revision=true`: o tamanho não autentica a versão, não detecta alterações de mesmo tamanho e não substitui hash/identidade/revisão confirmada. Fonte consultada: [notas técnicas da comunidade USUM](https://github.com/isleep2late/Un-Nerf-Compendium/blob/main/gen7_usum/azahar-mods/README.md).
- Os testes sintéticos foram ampliados para verificar os candidatos de tamanho sem ler dados do jogo.
- A suíte integral executada no checkout completo `85bbe6eb91cc53ee596c674b551bc74ea5df4bb3` passou: **106 testes em 1,288 s, OK**; Python 3.14.4, GCC 15.2.0; matriz diferencial 96/96; verificador de segurança PASS com 33 caminhos indexados. [Run 40157669355](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40157669355).
- **Limite:** ainda não foi analisado nenhum executável real de Ultra Sun/Ultra Moon nesta CI. O passo real com dados de jogo depende do mantenedor executar o inspetor sobre os próprios arquivos locais extraídos da cópia que pode usar legalmente e manter o relatório/dados fora do Git. A ferramenta atual é intake, não disassembler, recompilador ou runtime.

## POC-002 — primeiro subconjunto Thumb-16 — 2026-10-25

- Adicionado `tools/thumb_subset_poc.py`, uma ferramenta independente da POC ARM A32, para uma sequência explícita de halfwords Thumb-16 sintéticos.
- Subconjunto implementado: `MOVS Rd,#imm8`, `ADDS Rd,#imm8`, `SUBS Rd,#imm8`, `CMP Rn,#imm8`, `B` incondicional, `B<cond>` para as 14 condições EQ..LE e `BX LR` como terminador exato. Operandos limitam-se a r0–r7 e imediatos de 8 bits.
- Os ramos usam o PC Thumb (instrução atual + 4); alvos fora da fixture são rejeitados. Desvios para trás/autoalvos são recusados sem orçamento e limitados a 1–100.000 passos quando o orçamento é fornecido.
- A fixture sintética padrão deve retornar r0=7 com NZCV=6; a matriz nativa usa uma tabela independente para as 224 combinações de 14 condições × 16 estados NZCV. Foram adicionados 27 métodos de teste para decodificação, rejeições, CLI, compilação C11, flags, condição e orçamento.
- **Limite:** isto não identifica automaticamente instruções, não descobre funções e não deve ser aplicado por linear sweep a todo `.text`; literal pools, dados embutidos e transições entre ARM/Thumb requerem análise de fluxo. Nenhum dado de jogo foi usado.
- **Execução integral aprovada:** [run 40158610342](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40158610342), commit `f14aa07a23867fd3bd79c547006bcce57f8b2006`. Python 3.14.4, GCC 15.2.0; `Ran 136 tests in 1.946s`, `OK`; matriz diferencial 96/96, matriz Thumb 224 combinações, verificador de segurança PASS em 36 caminhos indexados e zero arquivos não ignorados não rastreados.
- **Correção observada na primeira execução:** o teste de `BX LR` esperava uma mensagem específica para instruções após o retorno, mas o tradutor gerava primeiro a mensagem de retorno ausente. A ordem das validações foi corrigida no commit `f14aa07a23867fd3bd79c547006bcce57f8b2006`; a execução integral seguinte passou.

## Ajustes de fidelidade estrutural do intake — 2026-10-25

- O inspetor agora lê o Program ID de 64 bits embutido no ACI do ExHeader (offset `0x200`), exige pelo menos `0x208` bytes para consultar esse campo e rejeita IDs conhecidos do jogo oposto. `--title-id` continua sendo um dado separado, opcional, do contêiner NCCH.
- A verificação do `.code` passou a exigir que o comprimento descomprimido corresponda exatamente à soma das alocações page-padded de `.text`, `.rodata` e `.data`. O relatório informa `code_file_offset` para cada segmento. Referência do formato: [3dbrew ExHeader](https://www.3dbrew.org/wiki/Exheader) e [LOADER:LoadProcess](https://www.3dbrew.org/wiki/LOADER%3ALoadProcess).
- **Validação integral:** workflow [run 40158271156](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40158271156), commit `c05ae90e6ea6f201f597cca1e00b851311ee3c73`: 109 testes aprovados, matriz diferencial 96/96 e verificador de segurança PASS (33 caminhos).
- **Limite:** nenhum ExHeader real ou `.code` real foi fornecido ao runner; os testes dessas regras usam metadados/bytes sintéticos. A etapa prepara a análise dos alvos, mas não confirma versão nem recompila o jogo.

## Inspeção local de um intervalo explícito ARM/Thumb — 2026-10-25

- Adicionados `tools/inspect_3ds_code_range.py` e `tests/test_inspect_3ds_code_range.py`; o guia é `docs/CODE_RANGE_INSPECTION.md`.
- A ferramenta recebe endereço virtual, estado de instrução e contagem explícitos. Mapeia o endereço para o offset do `.code` descomprimido usando o layout ExHeader, restringe a leitura ao payload declarado `.text` e decodifica apenas os subconjuntos ARM A32/Thumb conhecidos.
- Rejeita Program ID de jogo oposto ou não reconhecido (salvo override explícito), endereço desalinhado, leitura fora de `.text`, intervalo que entra no page padding e instruções não suportadas. Apresenta destinos dos branches sem descobrir funções.
- **Execução integral aprovada:** [run 40158948344](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40158948344), commit 78bad708b8e561d58f934f133fef68d9e1d1f2cb. Python 3.14.4/GCC 15.2.0; Ran 151 tests in 1.366s; OK; matriz diferencial 96/96; matriz Thumb 224 estados; verificador de segurança PASS com 38 caminhos indexados e zero arquivos não ignorados não rastreados.
- **Limite:** nenhum ExHeader ou `.code` real foi lido na CI; a nova ferramenta foi validada com arquivos sintéticos. Não descobre funções, não decide ARM/Thumb automaticamente, não resolve literal pools/calls/memória/ABI e não produz C executável. Os relatórios contêm encodings e devem permanecer locais.

## Inspeção parcial ARM/Thumb e prevenção de desalinhamento Thumb-2 — 2026-10-25

- `tools/inspect_3ds_code_range.py` agora oferece `--include-unsupported`: encodings desconhecidos ficam no relatório como bytes brutos, sem um mnemônico ou IR inventado. O modo estrito continua sendo o padrão.
- Prefixos Thumb-2 de 32 bits são agrupados como uma única instrução bruta de quatro bytes; o scanner não tenta decodificar a segunda metade separadamente. O formato e a semântica do Thumb-2 completo continuam fora do escopo.
- O tamanho final do intervalo é variável no estado Thumb quando um prefixo de 32 bits aparece. O relatório aponta offsets, endereços e se targets de branch caem no intervalo ou coincidem com um início de instrução escaneada.
- **Execução integral aprovada:** [run 40189160109](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40189160109), commit `7f333bea0355ed359ae78c23b2986f35fc5d4e1a`: `Ran 156 tests in 1.992s`, `OK`; matriz diferencial 96/96; verificador de segurança `PASS`, com 39 caminhos indexados.
- Cinco novos testes cobrem rejeição estrita de Thumb-2, agrupamento de 32 bits e alinhamento da instrução seguinte, encodings desconhecidos ARM/Thumb, e fronteira `.text`. Nenhum dado real de jogo foi usado na CI.
- Ainda falta decodificador Thumb-2 e uma entrada local autorizada; não há descoberta automática de funções, tradução integral do executável nem runtime do jogo.

## Decodificação de BL/BLX imediato Thumb na inspeção explícita — 2026-10-25

- **Família escolhida:** chamada Thumb `BL`/`BLX` (imediato), a única família de controle de fluxo de 32 bits desta etapa. Como o ARM11 do 3DS é ARMv6K e não implementa Thumb-2, a especificação aceita só o par prefixo/sufixo ARMv6K: `11110 imm11` seguido de `11111 imm11` (BL) ou `11101 imm11` com bit 0 zerado (BLX). `PC = endereço + 4`; offset = `(SignExt11(hi) << 12) + (lo << 1)`; BL permanece em Thumb em `PC + offset`; BLX entra em ARM em `Align4(PC + offset)`. O bit 0 ligado no sufixo BLX é recusado por conservadorismo. As formas Thumb-2 com J1/J2 e quaisquer outros pares de 32 bits continuam sem decodificação.
- **Código:** `decode_call_pair` e `call_target` em `tools/thumb_subset_poc.py`; `tools/inspect_3ds_code_range.py` passa a emitir `BL`/`BLX` como uma instrução de 4 bytes com `branch_target_virtual_address`, `branch_target_state`, `branch_target_within_declared_text`, `link_register_value` e `decoded_ir = ["call", kind, offset]`. Destino fora de uint32 não faz wraparound: em modo estrito falha com endereço; com `--include-unsupported` o par fica bruto (`unsupported-thumb32`) e o alinhamento seguinte é preservado. Um destino BLX (estado ARM) nunca é marcado como início de instrução Thumb escaneada. O tradutor `translate()` continua sem aceitar calls.
- **Testes:** 10 novos em `ThumbCallPairTests` (offsets hand-derivados nos limites, `bl .`, bit 0 do BLX, varredura de todos os 65536 valores de prefixo/sufixo, entradas inválidas, limites de uint32) e 9 novos no inspetor (BL/BLX, alinhamento do BLX, alvo fora de `.text`, alvo abaixo de zero, pares Thumb-2 não confundidos, fim de `.text`, estado ARM, CLI). Três testes antigos que usavam `F000 F800` como "desconhecido" passaram a usar `F000 0000`, pois `F000 F800` agora é um BL +0 válido. Mutantes manuais (sem alinhamento, PC+2, `lo<<2`, sem regra de bit 0) são detectados.
- **Limites:** sintaxe e cálculo de endereço apenas; não resolve função chamada, uso de LR, ABI, nem se o destino realmente é código. Um prefixo isolado ainda consome duas meias-palavras como entrada bruta (comportamento anterior preservado). Nenhum `.code` real foi lido; nenhum suporte a jogo é declarado.
- **Validação:** workflow [run 40189994092](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40189994092), commit `cc6ae6c71d28c4f13d91c00935d1755e56584d4e`: todos os passos aprovados (sintaxe Python, matriz diferencial, suíte completa, verificador de segurança). `Ran 175 tests ... OK` foi observado na execução local com os mesmos comandos; a contagem não foi extraída do log da CI.

## Decodificação de BX/BLX Rm e POP {..., PC} Thumb-16 — 2026-10-25

- **Especificação (ARMv6K, conservadora):** `BX Rm` = `0100 0111 0 Rm 000`; `BLX Rm` = `0100 0111 1 Rm 000`; `POP {reglist, PC}` = `1011 110 1 reglist8`. Bits 2:0 diferentes de zero são recusados; `Rm = PC` é recusado em ambos (BLX PC é imprevisível; BX PC depende de alinhamento e não é modelado); `POP` sem PC não é controle de fluxo e continua desconhecido; `0x4770` segue como `return`.
- **Código:** novos IR `("bx", rm)`, `("blx_reg", rm)` e `("pop_pc", reglist)` em `tools/thumb_subset_poc.py`. O tradutor sintético (`translate`) recusa essas formas explicitamente, pois não modela destinos indiretos nem pilha. O inspetor formata `BX r3`, `BLX r2`, `POP {r4, pc}`, marca `indirect_branch`, mantém `branch_target_virtual_address` nulo e informa `link_register_value = (endereço + 2) | 1` para `BLX Rm`.
- **Testes:** 6 novos em `ThumbIndirectFlowTests` (formas válidas, PC e bits SBZ, POP com/sem PC, classificação exaustiva de `0x4700..0x47FF` e `0xBC00..0xBDFF`, recusa pelo tradutor) e 4 no inspetor (decodificação e metadados, varredura linear continua, formas recusadas em modo estrito e bruto, estado ARM). Um bug real foi pego pelos testes durante a implementação (máscara do BX engolia o BLX) e corrigido; mutantes das máscaras e da regra de PC são detectados.
- **Limites:** só sintaxe. Destino real, troca ARM/Thumb por bit 0, conteúdo da pilha e se o `BX`/`POP` encerra uma função não são resolvidos; nenhum `.code` real foi lido; nenhum suporte a jogo é declarado.
- **Validação:** workflow [run 40192805813](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40192805813), commit `b7a69703ac80c77c0dce67caae634407f7316245`: aprovado (sintaxe, matriz diferencial, suíte completa, verificador de segurança). `Ran 185 tests ... OK` e matriz 96/96 foram observados na execução local com os mesmos comandos; a contagem não foi extraída do log da CI.

## Decodificação de PUSH/POP Thumb-16 com delta de pilha — 2026-10-25

- **Especificação:** `PUSH {reglist[, LR]}` = `1011 010 R reglist8`; `POP {reglist}` = `1011 110 0 reglist8` (o `POP {…, PC}` anterior é `1011 110 1`). Lista vazia sem LR/PC (`0xB400`, `0xBC00`) é imprevisível e recusada; `PUSH {lr}` (`0xB500`) é válida. Os vizinhos `0xB300`, `0xB600..0xB6FF`, `0xBA00`, `0xBE00` e `0xBF00` continuam desconhecidos.
- **Código:** IR `("push", mask, lr)` e `("pop", mask)` em `tools/thumb_subset_poc.py`; o tradutor sintético recusa ambos (sem modelo de memória). O inspetor formata `PUSH {r4, r5, lr}` / `POP {r4, r5}` e informa `stack_delta_bytes` (−4·n no PUSH, +4·n no POP, contando LR/PC) também para `POP {…, PC}`. PUSH/POP comuns não recebem `indirect_branch` nem destino.
- **Testes:** 6 novos em `ThumbStackTransferTests` (formas, listas vazias, varredura exaustiva de `0xB400..0xB5FF` e `0xBC00..0xBCFF`, vizinhos desconhecidos, recusa pelo tradutor) e 2 no inspetor (prólogo/epílogo com deltas calculados à mão; instruções sem efeito de pilha). Testes anteriores que tratavam `0xBC10`, `0xBCFF`, `0xB400` e `0xB500` como desconhecidos foram atualizados. Mutantes (máscara ignorando LR, lista vazia aceita, sinal do delta, LR não contado) são detectados.
- **Limites:** só sintaxe e delta de SP. Conteúdo, alinhamento, layout de frame, ABI e limites de função não são resolvidos; nenhum `.code` real foi lido; nenhum suporte a jogo é declarado.
- **Validação:** workflow [run 40193093691](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40193093691), commit `61fa3e9959d2540b2dca16baf66e1f5603c1ff66`: aprovado (sintaxe, matriz diferencial, suíte completa, verificador de segurança). `Ran 193 tests ... OK` e matriz 96/96 foram observados na execução local com os mesmos comandos; a contagem não foi extraída do log da CI.

## Decodificação de LDR literal Thumb-16 (endereço do literal) — 2026-10-25

- **Especificação:** `LDR Rd, [PC, #imm8*4]` = `01001 Rd imm8` (`0x4800..0x4FFF`); `PC = endereço + 4`; literal em `Align4(endereço + 4) + imm8·4` (0..1020 bytes). Literal cujos 4 bytes não cabem em uint32 é recusado em vez de sofrer wraparound. O valor do literal **nunca é lido**.
- **Código:** IR `("ldr_literal", rd, offset_bytes)` e `literal_address()` em `tools/thumb_subset_poc.py`; o tradutor sintético recusa a forma (sem modelo de memória). O inspetor formata `LDR r0, [pc, #20]` e informa `literal_pool_virtual_address`, `literal_within_declared_text` (4 bytes dentro do `.text`), `literal_value_read: false`, `literal_overlaps_selected_range` e `literal_is_scanned_instruction_start` — o último indica dado provavelmente decodificado como código dentro do intervalo escolhido.
- **Testes:** 5 novos em `ThumbLiteralLoadTests` (formas, varredura exaustiva de `0x4800..0x4FFF` e vizinhos, alinhamento de endereços com `%4 == 0` e `== 2`, limites de uint32, entradas malformadas, recusa pelo tradutor) e 5 no inspetor (endereço calculado à mão, literal dentro do intervalo escaneado, alinhamento a partir de endereço meia-palavra, literal fora/na borda do `.text`, estado ARM). Mutantes (sem alinhamento, offset·2, borda de 4 bytes no uint32, borda de 4 bytes no `.text`) são detectados.
- **Limites:** só endereço estático. Não lê o literal, não delimita pools, não decide se o conteúdo é dado ou código, não resolve relocations; nenhum `.code` real foi lido; nenhum suporte a jogo é declarado.
- **Validação:** workflow [run 40193521160](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40193521160), commit `fd876cf98965519203a000a9d9ce2c1999147256`: aprovado (sintaxe, matriz diferencial, suíte completa, verificador de segurança). `Ran 203 tests ... OK` e matriz 96/96 foram observados na execução local com os mesmos comandos; a contagem não foi extraída do log da CI.

## Continuação após LDR literal: grafo candidato de fluxo de controle — 2026-10-25

- Adicionado `tools/arm_thumb_cfg.py`, integrado ao JSON de `tools/inspect_3ds_code_range.py` pela chave `control_flow`.
- O módulo agrupa instruções em blocos básicos candidatos e registra arestas de branch condicional (tomada/não tomada), branch incondicional e fallthrough; branch para alvo fora do trecho é registrado como fronteira e um alvo que não coincide com início de instrução não é adivinhado.
- Chamadas BL/BLX viram transferências candidatas com continuação possível; BX/POP PC e outras transferências indiretas ficam sem destino fictício. Instruções desconhecidas encerram o bloco e bloqueiam arestas conhecidas. LDR literal que sobrepõe o trecho gera aviso de possível dado embutido.
- Adicionados testes sintéticos para fluxo linear, branches condicionais/incondicionais, loop, destino desalinhado, destino fora do range, calls, fluxo indireto, instrução desconhecida e literal-pool overlap; também foi adicionada cobertura integrada no inspetor.
- O resultado continua limitado a intervalos escolhidos explicitamente. Não lê o valor literal, não descobre funções e não deve ser tratado como CFG real validado contra Ultra Sun/Ultra Moon até uma entrada local autorizada ser examinada.

## Ampliação Thumb-1: ADD/SUB de três operandos — 2026-10-25

- A família implementada após LDR literal e grafo candidato de fluxo é Thumb-1 `00011 I op Rm/imm3 Rn Rd`: `ADDS/SUBS Rd, Rn, Rm` e `ADDS/SUBS Rd, Rn, #imm3`. Todos os registradores são R0–R7; essas formas atualizam NZCV. Referência do encoding: ARM Architecture Reference Manual, Thumb Instruction Set Encoding, Add/Subtract Register/Immediate ([manual ARMv6](https://www.scs.stanford.edu/~zyedidia/docs/arm/armv6.pdf)).
- A POC-002 emite C com soma alargada em `uint64_t` para carry, sem-borrow para C na subtração e fórmulas explícitas de overflow assinado. Memória, stack e calls permanecem fora da tradução.
- Testes adicionados: quatro formas de decodificação, classificação exaustiva do espaço `0x1800..0x1FFF`, compilação/execução de duas funções nativas cobrindo os casos immediate3/register, e formatação de mnemônicos pelo inspetor de intervalo.
- A verificação integral desta mudança está pendente neste registro; nenhum ExHeader ou `.code` real foi usado. O resultado valida a POC sintética, não gameplay.
