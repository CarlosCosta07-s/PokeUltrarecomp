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
| `ANDS Rdn, Rm` | AND entre registradores; atualiza N/Z e preserva C/V |
| `EORS Rdn, Rm` | XOR; atualiza N/Z e preserva C/V |
| `ADCS Rdn, Rm` | Soma com carry de entrada; atualiza NZCV |
| `SBCS Rdn, Rm` | Subtração com borrow derivado de C; atualiza NZCV |
| `TST Rn, Rm` | AND somente para flags; não altera Rn |
| `RSBS Rdn, Rm, #0` | Negação; inclui teste de overflow de 0x80000000 |
| `CMP Rdn, Rm` | Subtrai para NZCV sem alterar Rdn |
| `CMN Rdn, Rm` | Soma para NZCV sem alterar Rdn |
| `ORRS Rdn, Rm` | OR; atualiza N/Z e preserva C/V |
| `BICS Rdn, Rm` | AND com complemento; atualiza N/Z e preserva C/V |
| `MVNS Rd, Rm` | Complemento bit a bit; atualiza N/Z e preserva C/V |
| `ANDS Rdn, Rm` | AND entre registradores; atualiza N/Z e preserva C/V |
| `EORS Rdn, Rm` | XOR entre registradores; atualiza N/Z e preserva C/V |
| `ORRS Rdn, Rm` | OR entre registradores; atualiza N/Z e preserva C/V |
| `BICS Rdn, Rm` | AND com complemento; atualiza N/Z e preserva C/V |
| `MVNS Rd, Rm` | Complemento bit a bit; atualiza N/Z e preserva C/V |
| `TST Rn, Rm` | AND somente para flags; não altera Rn |
| `CMP Rdn, Rm` | Subtrai para NZCV sem alterar Rdn |
| `CMN Rdn, Rm` | Soma para NZCV sem alterar Rdn |
| `RSBS Rdn, Rm, #0` | Negação; atualiza NZCV, incluindo overflow de 0x80000000 |
| `LSL Rd, Rm, #imm5` | Desloca à esquerda; `LSL #0` preserva C |
| `LSR Rd, Rm, #imm5` | `LSR #0` é deslocamento de 32 bits e copia o bit 31 para C |
| `ASR Rd, Rm, #imm5` | `ASR #0` é deslocamento aritmético de 32 bits |
| `ADDS Rd, Rn, Rm` | Soma registradores baixos e atualiza NZCV |
| `SUBS Rd, Rn, Rm` | Subtrai registradores baixos e atualiza NZCV |
| `ADDS Rd, Rn, #imm3` | Soma imediato de 3 bits e atualiza NZCV |
| `SUBS Rd, Rn, #imm3` | Subtrai imediato de 3 bits e atualiza NZCV |
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

A cobertura inclui também deslocamentos imediatos Thumb-1 (LSL/LSR/ASR), operações lógicas/teste entre registradores (ANDS/EORS/ORRS/BICS/MVNS/TST), CMP/CMN entre registradores e RSBS Rdn,Rm,#0. Operações lógicas/teste preservam C/V, CMP/CMN não alteram o registrador comparado, e RSBS valida o overflow de negação do valor mínimo. Encodings de outros opcodes no mesmo espaço de data-processing continuam rejeitados.

O grupo Thumb-1 de processamento entre registradores agora cobre seus 16 opcodes: ANDS/EORS/LSLS/LSRS/ASRS/ADCS/SBCS/RORS/TST/RSBS/CMP/CMN/ORRS/MULS/BICS/MVNS. MULS grava os 32 bits inferiores do produto, atualiza N/Z e preserva C/V. Os shifts por registrador usam Rs[7:0] como quantidade, incluindo os casos 0, 32 e maior que 32, e são verificados com compilação C nativa. O decoder é um subconjunto delimitado de Thumb-1, não um decoder Thumb completo.

A cobertura inclui também os deslocamentos imediatos Thumb-1 LSL, LSR e ASR. Os testes classificam todos os encodings de 0x0000 a 0x17FF e executam testes C nativos para carry, preservação de C/V e os casos em que imm5=0 tem significado especial.

A cobertura inclui agora a família Thumb-1 de três operandos ADD/SUB (registrador ou imediato de 3 bits). Todos os encodings no intervalo 0x1800..0x1FFF são classificados nos testes; a execução nativa verifica carry/no-borrow, overflow e resultados. Isso não adiciona acesso à memória nem chamadas.

## Limites

Isto não é um disassembler geral nem um recompilador de jogos. Ainda faltam os formatos Thumb-1 restantes, Thumb-2 (não é o foco para ARMv6K), tradução de BL/BLX, BX/BLX Rm, PUSH/POP e POP {..., PC} (apenas a inspeção explícita de intervalos decodifica essas formas; o tradutor sintético as recusa), tradução de literal loads (a inspeção explícita só calcula o endereço do literal, sem ler o valor), acesso à memória, stack, calls, funções descobertas, relocations, CRO e ABI real. O scanner não deve ser aplicado a todo `.text` como se cada halfword fosse instrução: áreas de dados/literal pools e transições ARM/Thumb exigem análise de fluxo e proveniência.

Nenhuma ROM, dump, chave, firmware, ExHeader real ou byte de `.code` foi usado em testes. A validação cobre apenas as fixtures sintéticas da POC-002. A etapa que conecta um range ARM/Thumb identificado no executável local aos tradutores ainda está pendente.

## Evidência de validação — POC-002

A validação integral mais recente, no commit `aebc07b88024de06e899ae849f1fd33c026012a7`, passou em **234 testes, zero falhas e zero ignorados**. O runner usou Python 3.14.4 e GCC 15.2.0; a matriz diferencial foi 96/96 e o verificador de segurança passou em 41 caminhos indexados, com zero arquivos não ignorados e não rastreados. [Run reproduzível](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40197061451). Nenhum `.code` real foi lido; a evidência é sintética.
