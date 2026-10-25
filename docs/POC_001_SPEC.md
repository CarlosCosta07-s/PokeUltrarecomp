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

- ARM A32, condição AL (incondicional) apenas.
- `MOV`, `SUB`, `ADD`, `AND`, `ORR`, `EOR`, `BIC` e `MVN` imediatos sem atualização de flags.
- Imediatos com rotação ARM de 32 bits.
- Registradores limitados a `r0-r3`.
- `BX LR` como terminador único no final da sequência.
- Limite de 256 palavras de instrução por sequência.

Instruções condicionais, Thumb, operações com flags no tradutor, registradores fora do subconjunto, acessos à memória, saltos internos, exceções, ABI real do jogo, VFP/NEON, syscalls e dispositivos 3DS não são suportados. Código C gerado não deve ser usado com executáveis/dados proprietários nem como runtime de jogo.

## Modelo NZCV e integração restrita do tradutor

O módulo [tools/arm_flags.py](../tools/arm_flags.py) mantém uma referência imutável/testável das flags N, Z, C e V para aritmética uint32 e resultados lógicos. Inclui soma com carry-in, subtração com borrow-in, carry/no-borrow, overflow assinado e preservação/substituição do carry em operações lógicas.

**Integração mínima concluída:** o C gerado agora tem assinatura `uint32_t synthetic_entry(uint8_t *nzcv_out)` e pode retornar NZCV como nibble `N:bit3, Z:bit2, C:bit1, V:bit0`. O decodificador aceita `ADDS`, `SUBS` e `CMN` imediatos sob condições restritas; `CMN` atualiza flags sem escrever no registrador de destino. Testes C compilados verificam overflow de `ADDS`, carry/overflow em `SUBS` e as flags de `CMN`. O módulo `arm_flags.py` permanece um modelo de referência separado, e ainda não há representação CPSR completa. Formas lógicas com bit S, shifter-carry e desvios condicionais continuam recusadas até uma futura integração/teste end-to-end.

## Arquivos

- Implementação: [`tools/arm_subset_poc.py`](../tools/arm_subset_poc.py)
- Testes: [`tests/test_arm_subset_poc.py`](../tests/test_arm_subset_poc.py)

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

## Evidência atual e limites

- Python: verificação sintática aprovada.
- Suíte do tradutor POC-001: **31 testes aprovados**, incluindo decodificação de `ADDS`, `SUBS` e `CMN`, testes negativos e compilação/execução nativa de fixtures com NZCV esperado.
- Modelo de flags NZCV de referência: 18 testes aprovados, cobrindo resultados uint32, carry/borrow, overflow assinado, N/Z e preservação/substituição de C em operações lógicas.
- Suíte completa das ferramentas Python: **58 testes aprovados**, sem falhas ou testes ignorados (31 do tradutor, 18 do modelo NZCV e 9 do verificador de segurança).
- Prova host nativa: C gerado compilado com GCC e o executável foi executado; o resultado 12 foi confirmado pelo código de saída zero.
- Plataforma verificada: Linux x86-64 no ambiente da sessão; Windows ainda não testado.
- Não houve compilação do runtime do jogo nem execução de Pokémon.
- Essa POC valida o encadeamento *decodificação sintética → emissão C → compilador host → resultado* para dez palavras da fixture (nove operações e o terminador). Não demonstra cobertura útil para um jogo real nem substitui o teste de referência 001.
- A POC foi escrita de forma independente. O issue de procedência/escopo do `LICENSE` preexistente continua aberto; a publicação desta demonstração não resolve essa decisão de licenciamento.

## Próximos passos

1. Resolver a pendência de licença/procedência registrada em [issue #1](https://github.com/CarlosCosta07-s/PokeUltrarecomp/issues/1).
2. Executar o verificador de repositório contra uma cópia de trabalho completa da `main`.
3. Construir validação diferencial com um emulador independente/licenciado, comparando resultado e NZCV para fixtures sintéticas.
4. Definir o estado inicial de NZCV/CPSR e a política de preservação de flags na ABI da função gerada.
5. Só então ampliar formas aritméticas/lógicas com bit S ou implementar desvios condicionais; não chamar esta POC de runtime ou porta nativa.
