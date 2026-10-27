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

## Modelo de memória nativo limitado (API experimental)

O tradutor oferece um modo opcional, usado pela CI somente com instruções sintéticas:

```python
translate(
    halfwords,
    max_execution_steps=limite_finito,
    runtime_state_io=True,
    runtime_memory_io=True,
)
```

Este modo emite operações C normais que o compilador host traduz em instruções nativas. O código gerado recebe um buffer de bytes, uma base guest e um tamanho. É um modelo simples de endereçamento, não uma CPU virtual: não há decodificação/interpretação de instruções durante a execução, nem fallback para instruções não suportadas.

O subconjunto coberto é:
- Loads/stores por registrador: `STR/LDR`, `STRH/LDRH`, `STRB/LDRB`, `LDRSB` e `LDRSH`.
- Loads/stores com deslocamento imediato: word, halfword e byte (`STR/LDR`, `STRH/LDRH`, `STRB/LDRB`).
- `LDR Rd, [PC, #imm]` (literal): usa o endereço de entrada Thumb informado pelo host, calcula `Align(entry + índice*2 + 4, 4) + imm*4`, verifica overflow de endereço e limites do buffer e só então lê quatro bytes little-endian. Exige endereço de entrada halfword-aligned.
- `STR/LDR Rt, [SP, #imm]` word-relativo: usa o `SP` explícito recebido do host, calcula `SP + imm*4` em aritmética de 64 bits para detectar overflow de endereço de 32 bits e valida alinhamento e a região antes do store/load.
- `PUSH {reglist[, LR]}` e `POP {reglist}` (sem `PC`): `PUSH` decrementa o `SP`, guarda os registradores baixos em ordem crescente e, se solicitado, coloca `LR` por último; `POP` lê os registradores baixos em ordem crescente e incrementa o `SP`. A transferência inteira é validada antes de modificar o buffer/registradores; underflow/overflow do `SP`, desalinhamento e falta de mapeamento retornam status explícito, mantendo atômica a instrução com falha.
- `ADD SP, #imm7*4` e `SUB SP, #imm7*4`: no modo experimental de estado guest, ajustam o `SP` explícito com detecção de overflow/subfluxo; não leem/escrevem memória e não alteram NZCV. O `SP` final é devolvido pela ABI nativa versionada. Sem `runtime_memory_io=True`, continuam rejeitados.
- Transferência de vários registradores: `LDMIA` e `STMIA`, transferindo registradores da lista em ordem crescente. A região total é verificada antes de qualquer leitura/gravação; `STMIA` atualiza a base, enquanto `LDMIA` suprime o write-back quando a base está na lista. Por segurança, o subconjunto recusa `STMIA` quando a base está na lista.

Os acessos são emitidos bytewise em little-endian. O código verifica a validade dos argumentos, o intervalo de endereço de 32 bits, os limites do buffer e o alinhamento natural de acessos multibyte, além de usar código de status explícito: 0 (retorno), 1 (orçamento esgotado), 2 (mapeamento/entrada inválida), 3 (fora da região) e 4 (desalinhamento). O `PokeNativeCall` da ABI C versão 4 carrega o endereço de entrada, `SP` e `LR`; o `PokeNativeResult` retorna o `SP` final. As instruções `PUSH/POP` usam uma assinatura nativa específica com saída explícita de `SP`. Testes verificam falhas de faixa, desalinhamento e overflow sem leitura fora do buffer nem alteração parcial de memória, registradores ou `SP` na instrução com falha.

O modelo e a política de alinhamento são apenas um contrato de teste sintético. Eles não demonstram o mapeamento das regiões de memória reais de Ultra Sun/Ultra Moon nem a semântica completa de acessos desalinhados da CPU ARM11. O modo CLI normal continua sem ativar esse parâmetro. `LDR` literal, `STR/LDR` word relativos ao `SP` e `PUSH/POP` de registradores baixos estão cobertos apenas pela API experimental com `runtime_memory_io=True`. `POP {PC}`, `ADR` e outras formas de geração de endereço PC/SP continuam recusadas. `LDMIA/STMIA` também são aceitos apenas no modo experimental de memória limitado.

## Limites

Isto não é um disassembler geral nem um recompilador de jogos. O inspetor de intervalos reconhece load/store Thumb-1 por registrador, offsets imediatos e SP-relativos, transferências `LDMIA/STMIA`, `ADR` e ajustes de SP, fornecendo mnemônicos e metadados estáticos; não lê os valores dos acessos nem resolve registradores em tempo de execução. O tradutor padrão/CLI continua a recusar a maioria dos acessos a memória. Apenas a API experimental `translate(..., runtime_state_io=True, runtime_memory_io=True, max_execution_steps=N)` aceita o subconjunto limitado descrito acima e gera C nativo para uma região de memória byte-array fornecida pelo host. `LDR` literal PC-relative, `STR/LDR` word relativos ao `SP` e `PUSH/POP` sem `PC` estão cobertos; `ADR` e outras formas de geração de endereço PC/SP continuam rejeitadas na tradução. `LDMIA/STMIA` só são traduzidos no modo experimental limitado, com as regras e as combinações conservadoras descritas acima. A política de falhar em acessos multibyte desalinhados é uma guarda do modelo sintético, não prova a semântica exata de alinhamento da CPU ARM11. Ainda faltam outras famílias Thumb-1, a maioria de Thumb-2 (não é o foco para ARMv6K), regras de memória mais completas, ABI real e integração com código real do alvo. O scanner não deve ser aplicado a todo `.text` como se cada halfword fosse instrução: áreas de dados/literal pools e transições ARM/Thumb exigem análise de fluxo e proveniência.

Nenhuma ROM, dump, chave, firmware, ExHeader real ou byte de `.code` foi usado em testes. A validação cobre apenas as fixtures sintéticas da POC-002. A etapa que conecta um range ARM/Thumb identificado no executável local aos tradutores ainda está pendente.

## Evidência de validação — POC-002

A validação integral mais recente, no commit `aebc07b88024de06e899ae849f1fd33c026012a7`, passou em **234 testes, zero falhas e zero ignorados**. O runner usou Python 3.14.4 e GCC 15.2.0; a matriz diferencial foi 96/96 e o verificador de segurança passou em 41 caminhos indexados, com zero arquivos não ignorados e não rastreados. [Run reproduzível](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40197061451). Nenhum `.code` real foi lido; a evidência é sintética.


## Validação mais recente — 2026-10-27

O [workflow nativo #40499829597](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40499829597) passou em Linux/GCC e Windows/MSVC com **4/4 testes CTest por plataforma**. A suíte Python passou em **330 testes** no [workflow #40499829721](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40499829721). O host C++20 verifica `PUSH {r0, r1, LR}` e `POP {r2, r3}` nativos, a ordem dos valores, o `SP` final, underflow, overflow, desalinhamento e falhas de faixa sem escrita parcial. Todos os casos usam fixtures sintéticas; nenhum código ou mapa de memória real de Ultra Sun/Ultra Moon foi validado.
