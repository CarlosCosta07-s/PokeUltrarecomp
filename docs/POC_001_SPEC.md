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

## Modelo isolado de flags NZCV

O módulo [\`tools/arm_flags.py\`](../tools/arm_flags.py) implementa uma representação imutável das flags N, Z, C e V para aritmética de 32 bits e atualização de N/Z em operações lógicas. Inclui soma com carry-in, subtração com borrow-in, carry/no-borrow, overflow assinado e preservação de C/V em operações lógicas quando o shifter não produz um novo carry.

Esse modelo está **separado do tradutor ARM A32 → C**. Ainda não muda a emissão de C, não implementa o CPSR completo e não habilita instruções com o bit S. O módulo tem testes próprios em [\`tests/test_arm_flags.py\`](../tests/test_arm_flags.py). A integração com o tradutor e o suporte a instruções como CMN permanecem pendentes até existir uma representação de estado/flags na execução recompilada.

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
- Executável gerado termina com código zero apenas quando `synthetic_entry()` retorna 12.

## Evidência atual e limites

- Python: verificação sintática aprovada.
- Suíte do tradutor POC-001: 23 testes aprovados no ambiente temporário desta sessão.
- Modelo de flags NZCV isolado: 18 testes aprovados, cobrindo resultados de 32 bits, carry, borrow, overflow assinado, N/Z e preservação/substituição de C nas operações lógicas.
- Suíte completa das ferramentas Python: 50 testes aprovados, sem falhas ou testes ignorados (23 do tradutor, 18 do modelo NZCV e 9 do verificador de segurança).
- Prova host nativa: C gerado compilado com GCC e o executável foi executado; o resultado 12 foi confirmado pelo código de saída zero.
- Plataforma verificada: Linux x86-64 no ambiente da sessão; Windows ainda não testado.
- Não houve compilação do runtime do jogo nem execução de Pokémon.
- Essa POC valida o encadeamento *decodificação sintética → emissão C → compilador host → resultado* para dez palavras da fixture (nove operações e o terminador). Não demonstra cobertura útil para um jogo real nem substitui o teste de referência 001.
- A POC foi escrita de forma independente. O issue de procedência/escopo do `LICENSE` preexistente continua aberto; a publicação desta demonstração não resolve essa decisão de licenciamento.

## Próximos passos

1. Resolver a pendência de licença/procedência registrada em [issue #1](https://github.com/CarlosCosta07-s/PokeUltrarecomp/issues/1).
2. Validar o verificador de repositório contra uma cópia de trabalho completa da `main`.
3. Definir, com licença verificada, se a POC evolui como experimento independente ou se deve comparar-se a uma ferramenta de referência aprovada.
4. Só ampliar o subconjunto após adicionar testes positivos e negativos para cada instrução/semântica; não chamar esta POC de runtime ou porta nativa.
