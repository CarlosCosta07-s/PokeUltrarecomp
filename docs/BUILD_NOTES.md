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
- Blobs atuais verificados no GitHub: \`tools/arm_subset_poc.py\` = \`8ca13e7d9fd3e174ce0abedf55b541132a15b90a\`; \`tests/test_arm_subset_poc.py\` = \`39eddf42eef5929ca83c7447ffb0d61f1fc98d80\`; \`docs/POC_001_SPEC.md\` = \`c73c4573e1f74f55e4c792714711de75d8fb834c\`; \`README.md\` = \`c7b0d56ffe97aff6b3ad48df154f1ba9f6d19413\`; \`docs/ROADMAP.md\` = \`bd08d9d8d0e3c01630cc95e69d3bd520d3de348b\`.
- **Estado de validação desta iteração: PENDENTE.** A última suíte integral documentada no commit anterior tinha 85 testes aprovados. Esta mudança adiciona dois testes, o que leva a **87 testes esperados** (56 tradutor + 18 modelo NZCV + 9 verificador de segurança + 4 matriz diferencial), e amplia o teste nativo de condições. Não consegui executar a suíte desta versão nesta sessão: git clone https://github.com/CarlosCosta07-s/PokeUltrarecomp.git falhou porque o ambiente não conseguiu resolver github.com. Não afirmo que os novos testes passaram. Executar python3 -B -m unittest discover -s tests -v e python3 tools/arm_differential_poc.py num checkout sincronizado é o próximo critério de aceitação.
- Limites: predicação só é suportada para instruções dentro do subconjunto explícito; BL, condição 0xF, memória, Thumb, formas lógicas com S-bit e carry do shifter permanecem fora do escopo. Saltos para trás seguem bloqueados para não permitir loops sem orçamento de execução. Nenhum emulador foi usado; não existe equivalência com gameplay nem runtime próprio concluído.
