# POC-002 — subconjunto Thumb-16 para C

## Objetivo

Complementar a POC-001 ARM A32 com uma segunda demonstração independente e igualmente limitada. O tradutor recebe uma sequência explícita de halfwords Thumb-16 sintéticos, produz C e permite testar resultado, flags NZCV, desvios e limite de execução. Não tenta localizar funções dentro de um jogo, não reconhece limites ARM/Thumb, nem lê arquivos extraídos.

## Instruções implementadas

| Forma Thumb-1 | Comportamento na POC |
| --- | --- |
| `MOVS Rd, #imm8` | Escreve r0–r7; atualiza N/Z e preserva C/V |
| `ADDS Rd, #imm8` | Soma uint32; atualiza NZCV |
| `SUBS Rd, #imm8` | Subtrai uint32; atualiza NZCV |
| `CMP Rn, #imm8` | Subtrai para flags sem alterar o registrador |
| `B<cond> label` | Suporta as 14 condições EQ..LE |
| `B label` | Desvio incondicional |
| `BX LR` | Terminador/retorno; apenas o encoding exato é aceito |

Imediatos são de 8 bits. Registradores limitam-se a r0–r7, inicializados em zero; o resultado retorna em r0. A sequência deve terminar com `BX LR` e ter no máximo 256 halfwords. Instruções fora desse subconjunto são rejeitadas.

## Desvios e orçamento

Os offsets são decodificados em unidades de halfword com base no PC Thumb (endereço atual + 4). Alvos fora da sequência são rejeitados. Desvios para trás/autoalvos são recusados se não houver orçamento. Com `max_execution_steps` (1–100.000), o C gerado relata status 0 para retorno normal ou status 1 quando o orçamento se esgota; passos contam instruções visitadas, inclusive branches não tomados e `BX LR`.

## Reproduzir a fixture sintética

    python tools/thumb_subset_poc.py

A fixture padrão `MOVS r0,#12; SUBS r0,#8; ADDS r0,#3; CMP r0,#7; BX LR` deve retornar 7 e produzir NZCV=6. Para traduzir uma sequência explicitamente:

    python tools/thumb_subset_poc.py 200C 3808 3003 2807 4770

Executar testes:

    python -m unittest discover -s tests -v

A matriz nativa compara as 14 condições × 16 estados de entrada NZCV com uma tabela booleana independente. Outros testes compilam C com C11, `-Wall -Wextra -Werror` e executam um laço com término esperado e outro com orçamento esgotado.

## Limites

Isto não é um disassembler geral nem um recompilador de jogos. Ainda faltam os formatos Thumb-1 restantes, Thumb-2 (não é o foco para ARMv6K), BL/BLX, literal loads, acesso à memória, stack, calls, funções descobertas, relocations, CRO e ABI real. O scanner não deve ser aplicado a todo `.text` como se cada halfword fosse instrução: áreas de dados/literal pools e transições ARM/Thumb exigem análise de fluxo e proveniência.

Nenhuma ROM, dump, chave, firmware, ExHeader real ou byte de `.code` foi usado em testes. A validação cobre apenas as fixtures sintéticas da POC-002. A etapa que conecta um range ARM/Thumb identificado no executável local aos tradutores ainda está pendente.
