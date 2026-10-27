# POC-001 — demonstração sintética de tradução ARM A32 para C

## Estado

**Implementada como demonstração limitada; testes locais da POC aprovados no ambiente de desenvolvimento Linux desta sessão. Não é um recompilador geral, não testa jogo e não comprova suporte a Windows.**

## Objetivo

Comprovar, usando apenas uma fixture numérica sintética, que um decodificador pequeno consegue traduzir instruções ARM A32 explicitamente suportadas para C host, que o C gerado compila com um compilador C11 e que o executável produz o resultado esperado.

## Fixture e resultado esperado

A sequência sintética padrão é:

| Palavra ARM A32 | Interpretação limitada |
| --- | --- |
| `0xE3A0000C` | `MOV r0, #12` |
| `0xE2400008` | `SUB r0, r0, #8` |
| `0xE2800003` | `ADD r0, r0, #3` |
| `0xE2000007` | `AND r0, r0, #7` |
| `0xE3800008` | `ORR r0, r0, #8` |
| `0xE2200001` | `EOR r0, r0, #1` |
| `0xE3C00002` | `BIC r0, r0, #2` |
| `0xE3E01000` | `MVN r1, #0` |
| `0xE201000C` | `AND r0, r1, #12` |
| `0xE12FFF1E` | `BX LR` — terminador/retorno |

A função C gerada deve retornar `12`: `12 - 8 + 3 = 7`; `AND #7` mantém `7`, `ORR #8` produz `15`, `EOR #1` produz `14`, e `BIC #2` limpa o bit de valor 2, produzindo `12`; `MVN r1,#0` define `r1` como `0xFFFFFFFF`, e o último `AND` confirma que o valor 12 pode ser recuperado desse resultado. Não são lidos arquivos externos, ROMs, dumps, firmware, chaves ou recursos extraídos. Não há código de jogo nem código de terceiro no demonstrador.

## Subconjunto implementado

- ARM A32: as instruções de processamento de dados suportadas aceitam condições AL e EQ..LE; a condição `0xF` é recusada. `B` aceita AL e as 14 condições padrão EQ..LE.
- Formas imediatas de `MOV`, `SUB`, `ADD`, `AND`, `ORR`, `EOR`, `BIC` e `MVN` sem atualização de flags; as formas sem AL são executadas somente quando sua condição EQ..LE é verdadeira.
- Formas de operando em registrador sem deslocamento (`Operand2` com shift zero): `MOV/MVN`, `AND/ORR/EOR/BIC`, `ADD/SUB`, `ADDS/SUBS`, `CMN/CMP`, incluindo `MOVS/MVNS`, `ANDS/ORRS/EORS/BICS` e `TST/TEQ`. As formas predicadas seguem a condição A32 selecionada; `CMN/CMP/TST/TEQ` não escrevem no registrador de resultado.
- Nas operações lógicas com S-bit e `Operand2` sem shift, o tradutor atualiza N/Z e preserva C/V, conforme a semântica de shift zero. Isso está coberto por testes nativos sintéticos. Formas lógicas imediatas com S-bit, deslocamentos não zero, shifts por registrador, barrel shifter e carry derivado de um shift continuam recusados explicitamente. O suporte de registradores continua limitado a `r0-r3` e não inclui PC/SP/LR como operandos normais.
- Memória A32 (somente com `runtime_state_io=True`, orçamento explícito e `runtime_memory_io=True`): `LDR/STR` de palavra e `LDRB/STRB` de byte por offset imediato, pré-indexado, sem post-index ou writeback. O C gerado recebe `memory`, `memory_base` e `memory_size`, calcula os endereços com checagem de overflow, exige alinhamento de palavra nos acessos de 32 bits (byte accesses não exigem alinhamento) e valida todo o acesso dentro da região antes de ler/escrever. A ordem é little-endian. Estados de execução retornados: 0 (retorno), 1 (orçamento esgotado), 2 (estado/mapeamento inválido), 3 (falha de memória/overflow de endereço) e 4 (falha de alinhamento). Isso é uma região de teste limitada, não o mapa de memória do Nintendo 3DS.
- `B` incondicional e com as 14 condições padrão (EQ, NE, CS, CC, MI, PL, VS, VC, HI, LS, GE, LT, GT, LE), com destinos à frente dentro da própria fixture; os saltos preservam NZCV.
- Formas aritméticas imediatas com flags: `ADDS`, `SUBS`, `CMN` e `CMP`, com flags NZCV expostas em parâmetro de saída.
- Imediatos com rotação ARM de 32 bits.
- Registradores limitados a `r0-r3`.
- `BX LR` como terminador único no final da sequência.
- Limite de 256 palavras de instrução por sequência.

BL, o campo de condição 0xF (espaço BLX imediato), saltos para fora da fixture, instruções e opcodes fora do subconjunto explícito, Thumb, formas lógicas/MOVS/MVNS imediatas com S-bit, shifts não zero do Operand2, carry do barrel shifter, CPSR completo, registradores fora do subconjunto, outros acessos à memória A32 além de `LDR/STR` word e byte pré-indexados imediatos, chamadas/funções reais, exceções, ABI estável integrado ao host para A32-memory, VFP/NEON, syscalls e dispositivos 3DS não são suportados. Saltos para trás ou para a própria instrução são rejeitados por padrão e só podem ser traduzidos quando é fornecido um orçamento explícito de execução. Código C gerado não deve ser usado com executáveis/dados proprietários nem como runtime de jogo.

## Modelo NZCV e integração restrita do tradutor

O módulo [tools/arm_flags.py](../tools/arm_flags.py) mantém uma referência imutável/testável das flags N, Z, C e V para aritmética uint32 e resultados lógicos. Inclui soma com carry-in, subtração com borrow-in, carry/no-borrow, overflow assinado e preservação/substituição do carry em operações lógicas. No tradutor, `ADDS`, `SUBS`, `CMN` e `CMP` imediatos atualizam NZCV; desvios e instruções de dados condicionais consomem N, Z, C e V de acordo com a tabela de condições ARM. Uma instrução predicada que não satisfaz sua condição não modifica registradores nem flags.

**Integração mínima concluída:** o C gerado usa `uint32_t synthetic_entry(uint8_t *nzcv_out)` e retorna NZCV como nibble `N:bit3, Z:bit2, C:bit1, V:bit0`. O decodificador aceita `ADDS`, `SUBS`, `CMN` e `CMP` imediatos em condições restritas. `CMN` calcula flags de soma e `CMP` calcula flags de subtração, sem escrever o resultado no registrador de destino. Testes nativos cobrem os dois casos de comparação. O módulo `arm_flags.py` permanece um modelo de referência separado; ainda não há CPSR completo. Formas lógicas com bit S e shifter-carry continuam recusadas. Tanto `B` quanto as instruções de dados suportadas respeitam as 14 condições padrão de ARM. O teste nativo compila 448 funções (224 de desvio e 224 de predicação de dados; 14 condições × 16 estados de entrada de NZCV por tipo) e compara os caminhos executados com uma tabela de condições escrita de forma independente no teste; a revisão anterior também detectou uma mutação deliberada de `GT` (4 divergências em 224).

**Estado inicial de NZCV (política definida):** a ABI continua sendo `synthetic_entry(uint8_t *nzcv_out)`, sem entrada de flags em tempo de execução. O estado de entrada é escolhido na geração, por `translate(words, initial_nzcv=...)` ou `--initial-nzcv` na CLI, como nibble `N:bit3 Z:bit2 C:bit1 V:bit0` (padrão 0, valores fora de 0..15 são rejeitados). Um desvio ou uma instrução de dados condicional sem uma instrução anterior que defina flags decide, portanto, pelo estado de entrada escolhido. Isso é uma convenção da POC, não uma afirmação sobre o CPSR real de qualquer chamador.

## Orçamento explícito para laços

Por padrão, `translate(words, initial_nzcv=0)` mantém a ABI antiga `uint32_t synthetic_entry(uint8_t *nzcv_out)` e rejeita desvios para trás/autoalvos. Para aceitar esses alvos, o chamador precisa passar `max_execution_steps` entre 1 e 100.000, ou usar `--max-execution-steps` na CLI. Nesse modo, o C emitido usa:

    uint32_t synthetic_entry_bounded(
        uint8_t *nzcv_out,
        uint32_t *steps_executed_out,
        uint8_t *execution_status_out
    );

Cada instrução de convidado visitada conta para o orçamento, incluindo um desvio, uma instrução predicada cuja condição seja falsa e o `BX LR` final. O status é 0 quando `BX LR` termina normalmente e 1 quando o limite é esgotado antes da próxima instrução; o contador informa quantos passos foram executados. Os ponteiros de saída de contador/status podem ser nulos, mas um chamador que precisa distinguir retorno normal de esgotamento deve fornecer `execution_status_out`. No esgotamento, o valor retornado e NZCV representam o estado parcial no instante em que o limite foi atingido, não um retorno normal do programa. O limite reduz risco de laço infinito em fixtures; não é uma sandbox nem prova de segurança para C arbitrário.

## Arquivos

- Implementação: [`tools/arm_subset_poc.py`](../tools/arm_subset_poc.py)
- Testes: [`tests/test_arm_subset_poc.py`](../tests/test_arm_subset_poc.py)

## Política para emuladores e referência externa

O objetivo do PokeUltrarecomp é investigar recompilação e execução nativas no Windows, não criar uma solução que dependa de um emulador de Nintendo 3DS. Os testes de instruções e de lógica da ferramenta devem priorizar fixtures sintéticas, resultados definidos pela especificação ARM e modelos de referência próprios testáveis. Nenhum emulador é necessário para a validação atual.

Se um dia for necessário observar o comportamento do jogo original para comparar uma parte recompilada, o Azahar é a opção externa indicada pelo mantenedor. Nesse caso, ele será apenas uma referência de comparação fora do runtime: não será ligado como dependência, embutido no produto final nem tratado como substituto da recompilação nativa. A integração de código de qualquer projeto externo exigiria avaliação separada de licença e escopo.

## Matriz diferencial sintética

A ferramenta [tools/arm_differential_poc.py](../tools/arm_differential_poc.py) monta 192 fixtures aritméticas, combinando oito valores de r0, três valores de operando e as formas imediatas e com operando em registrador de ADDS/SUBS/CMN/CMP. Ela compila o C emitido e compara o valor retornado e NZCV com o modelo separado `tools/arm_flags.py`. Os desvios têm testes nativos específicos adicionais para destinos, condição EQ/NE e caminhos tomados/não tomados. Execute com:

    python tools/arm_differential_poc.py

O teste compara o C gerado com o modelo NZCV separado do projeto; **não é validação contra um emulador independente** e não prova compatibilidade com o jogo. A matriz executou **192/192 correspondências** com C11, `-Wall -Wextra -Werror`, incluindo as formas recém-adicionadas de operando em registrador. Os testes nativos específicos de `B`, `BEQ` e `BNE` também passaram. Os hashes Git da implementação, testes, modelo de flags e matriz foram conferidos com os blobs correspondentes de `main`. Isso valida o conjunto Python verificado, não um checkout integral recém-clonado nem o jogo.

## Como reproduzir

Requisitos: Python 3.10+, Git e compilador C compatível com C11 (GCC ou Clang é o caminho testado nesta POC).

Gerar C para stdout:

    python tools/arm_subset_poc.py

Fornecer a fixture explicitamente (palavras hexadecimais):

    python tools/arm_subset_poc.py E3A0000C E2400008 E2800003 E2000007 E3800008 E2200001 E3C00002 E3E01000 E201000C E12FFF1E

Escrever o C em um arquivo local:

    python tools/arm_subset_poc.py --output synthetic_poc.c

Executar a suíte unitária e a compilação/execução nativa temporária:

    python -m unittest discover -s tests -v

O teste de compilação compila o C emitido dentro de um diretório temporário, executa o binário e exige código de saída zero, correspondente ao retorno 12. Se nenhum compilador suportado for encontrado, esse teste é ignorado, e a comprovação de execução nativa permanece incompleta.

## Critérios de aceitação

- Decodificação de cada uma das dez palavras exatas para a operação esperada.
- Decodificação correta de um imediato rotacionado sintético.
- Rejeição de condição não suportada, atualização de flags, registrador de origem/destino fora do limite, sequência sem `BX LR`, instruções após o retorno e sequência longa demais.
- C emitido passa por compilador C11 com avisos ativados e `-Werror` no ambiente que suportar essas opções.
- Executável gerado termina com código zero quando `synthetic_entry(&nzcv_out)` retorna 12 e o nibble NZCV corresponde ao caso de teste.
- Saltos para trás/autoalvos são rejeitados sem orçamento e, com orçamento explícito, o código gerado termina normalmente ou reporta `execution_status_out == 1` quando o limite é atingido.

## Evidência atual e limites

- Python: verificação sintática aprovada.
- Suíte do tradutor POC-001: **61 testes definidos**, incluindo a matriz nativa de 448 combinações e casos para laços com orçamento. Os 61 testes do tradutor também passaram isoladamente antes da execução combinada.
- Modelo de flags NZCV de referência: 18 testes aprovados, cobrindo resultados uint32, carry/borrow, overflow assinado, N/Z e preservação/substituição de C em operações lógicas.
- **Núcleo de testes POC-001:** 92 testes (61 do tradutor, 18 do modelo NZCV, 9 de segurança e 4 da matriz diferencial).
- **Suíte integral mais recente:** 106 testes aprovados, zero falhas e zero ignorados, no checkout completo do commit `85bbe6eb91cc53ee596c674b551bc74ea5df4bb3`, em Ubuntu com Python 3.14.4 e GCC 15.2.0. Os 14 testes adicionais cobrem o novo inspetor de alvos Ultra Sun/Ultra Moon. Sintaxe Python, matriz diferencial 96/96 e verificador de segurança também passaram; o verificador conferiu 33 caminhos indexados. [Execução reproduzível no GitHub Actions](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40157669355).
- **Verificação complementar parcial anterior:** a fonte do tradutor antes do suporte a orçamento (blob `8ca13e7d9fd3e174ce0abedf55b541132a15b90a`) foi executada num workspace isolado; a fixture padrão, a matriz de 448 casos e os harnesses condicionais passaram.
- **Validação isolada anterior:** os 61 testes do tradutor passaram num workspace temporário. A evidência principal agora é a execução integral de 106 testes acima. O teste de referência 001 permanece pendente, e Windows ainda não foi testado.
- Prova host nativa: C gerado compilado com GCC e o executável foi executado; o resultado 12 foi confirmado pelo código de saída zero.
- Plataforma verificada: Linux x86-64 no ambiente da sessão; Windows ainda não testado.
- Não houve compilação do runtime do jogo nem execução de Pokémon.
- Essa POC valida o encadeamento *decodificação sintética → emissão C → compilador host → resultado* para dez palavras da fixture (nove operações e o terminador). Não demonstra cobertura útil para um jogo real nem substitui o teste de referência 001.
- A POC foi escrita de forma independente. O issue de procedência/escopo do `LICENSE` preexistente continua aberto; a publicação desta demonstração não resolve essa decisão de licenciamento.

## Próximos passos

1. Resolver a pendência de licença/procedência registrada em [issue #1](https://github.com/CarlosCosta07-s/PokeUltrarecomp/issues/1).
2. Executar o verificador de repositório contra uma cópia de trabalho completa da `main`.
3. Ampliar a validação sintética baseada na especificação ARM, com casos esperados independentes para resultados, flags e limites; não é necessário usar emulador para essa etapa. Se futuramente uma comparação do comportamento do jogo original for realmente útil, o Azahar poderá ser usado somente como referência externa opcional, nunca como dependência do runtime.
4. ~~Definir o estado inicial de NZCV~~ — feito (ver "Estado inicial de NZCV"). Ainda aberta: a política de preservação de flags na ABI de uma função real, que exige evidência além desta fixture.
5. Predicação de dados e orçamento de execução: implementados para o subconjunto atual; a suíte combinada e o verificador de segurança passaram no runner descrito acima. Próximo critério: ampliar as fixtures independentes de flags/controle e depois considerar formas lógicas com bit S, que exigem modelar o carry do shifter. O teste de referência 001, Windows e a decisão sobre o `LICENSE` preexistente permanecem pendentes. Não chamar esta POC de runtime ou porta nativa.
