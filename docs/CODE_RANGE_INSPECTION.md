# Inspeção de um intervalo explicitamente selecionado do executável

## Escopo

O intake identifica metadados e layout, mas não adivinha onde uma função começa, se o código é ARM ou Thumb, ou se uma região contém dados embutidos. A ferramenta `tools/inspect_3ds_code_range.py` é a próxima etapa conservadora: o mantenedor indica o endereço virtual, o estado de instrução e a quantidade exata de instruções. A ferramenta valida o intervalo contra o `.text` declarado no ExHeader e decodifica somente esse trecho usando os subconjuntos já testados.

## Exemplo local

    python tools/inspect_3ds_code_range.py --target ultra-sun --exheader /local/exheader.bin --code /local/code.bin --state thumb --start-address 0x00100000 --instruction-count 8 --title-id 00040000001B5000

Para uma inspeção parcial de um intervalo que contém encodings não suportados, acrescente `--include-unsupported`. O relatório identifica entradas como `unsupported` ou `unsupported-thumb32`, mantém o encoding bruto e continua a partir do próximo limite conhecido, sem inventar semântica.

Use endereços alinhados ao tamanho da instrução: múltiplos de quatro bytes para ARM A32 e de dois bytes para Thumb. Para Thumb, informe o endereço de instrução sem o bit de estado Thumb que pode estar presente em um ponteiro de função. O arquivo `.code` deve estar descomprimido e corresponder ao ExHeader.

O resultado é JSON para stdout. Para salvar, passe `--report /caminho/fora/do/repositorio/intervalo.json`; a ferramenta recusa gravar o relatório dentro da árvore do projeto. O relatório inclui encodings e mnemônicos, além de hashes e offsets locais, portanto deve permanecer privado quando derivado de um jogo.

## Guardrails

- Exige o Program ID embutido no ACI reconhecido como o alvo selecionado; para um identificador desconhecido, a ferramenta falha salvo quando o mantenedor passa explicitamente `--allow-unverified-target`.
- Só examina o payload `.text` declarado; não usa a região de page padding como código.
- Exige o estado ARM/Thumb e a contagem explicitamente. Não há descoberta de funções, linear sweep ou detecção automática de estado.
- Por padrão, se uma palavra/halfword estiver fora do pequeno subconjunto, falha na primeira instrução não suportada e apresenta o endereço.
- Com `--include-unsupported`, encodings desconhecidos são preservados como brutos, com `mnemonic` e `decoded_ir` nulos; o status geral muda para `partially-decoded-explicit-range`.
- Entre as formas Thumb de 32 bits, apenas o par `BL`/`BLX` imediato do ARMv6K é decodificado (`11110 imm11` + `11111 imm11` para BL; `11101 imm11` com bit 0 zerado para BLX). O relatório informa `branch_target_virtual_address`, `branch_target_state` (`thumb` para BL, `arm` para BLX, com alinhamento a 4 bytes) e `link_register_value`. Destinos fora de 0..2^32-1 não sofrem wraparound: a instrução passa a ser tratada como desconhecida. Todos os demais pares de 32 bits (inclusive as formas Thumb-2 com J1/J2, que o ARM11 do 3DS não implementa) continuam agrupados em uma entrada bruta de 4 bytes, sem decodificação.
- Em Thumb-16, `BX Rm`, `BLX Rm` (Rm ≠ PC; bits 2:0 zerados) e `POP {reglist, PC}` são decodificados como fluxo indireto: o relatório marca `indirect_branch`, deixa `branch_target_virtual_address` nulo (o destino vem de registrador/pilha em tempo de execução) e, para `BLX Rm`, informa `link_register_value`. `BX LR` (`0x4770`) continua sendo `return`. `BX PC`, `BLX PC` e `POP` sem PC permanecem desconhecidos. A decodificação de um `BX`/`POP` não prova que uma função termina ali, e o intervalo continua sendo varrido linearmente.
- Em Thumb-16, `PUSH {reglist[, LR]}` e `POP {reglist}` são decodificados, junto com `POP {reglist, PC}`, e o relatório inclui `stack_delta_bytes` (negativo no PUSH). Listas vazias sem LR/PC são recusadas (imprevisíveis). Não há modelo de pilha, de alinhamento nem de convenção de chamada; um par PUSH/POP não prova o limite de uma função.
- Em Thumb-16, `LDR Rd, [PC, #imm]` é decodificado e o relatório informa `literal_pool_virtual_address` = `Align4(endereço + 4) + imm8·4`, `literal_within_declared_text` (os 4 bytes do literal dentro do `.text`) e `literal_value_read: false`: o valor nunca é lido. `literal_overlaps_selected_range` e `literal_is_scanned_instruction_start` sinalizam quando o literal cai dentro do intervalo varrido, isto é, quando dados podem estar sendo decodificados como instruções. Literais fora de uint32 são recusados; extensão do pool, literais compartilhados e o significado do valor não são resolvidos.
- Em Thumb-16, as famílias `STR/STRH/STRB/LDR/LDRH/LDRB/LDRSB/LDRSH` por registrador são decodificadas com `Rm`, base `Rn` e registrador de dados `Rt`; variantes de imediato aplicam o fator correto a `imm5` (×4/×1/×2), e variantes SP-relativas usam `imm8 × 4`. `memory_access` informa direção, largura, extensão de sinal, modo, base e offset. `LDMIA/STMIA` também reportam a lista, número de palavras, bytes transferidos, writeback e se o valor armazenado do registrador-base é arquiteturalmente desconhecido. `runtime_effective_address_resolved: false` e `memory_value_read_by_inspector: false` deixam claro que nenhum valor de registrador/memória é presumido.
- Thumb-16 `ADR`, `ADD Rd, SP, #imm8×4` e `ADD/SUB SP, #imm7×4` são também identificados: ADR calcula o alvo com `Align4(address + 4) + offset`; o relatório expõe base PC/alvo virtual e delta SP, sem avaliar o valor de SP ou o conteúdo de memória. Estas formas continuam recusadas pelo tradutor sintético por não ter modelo de PC/SP real.
- Informa os destinos calculados de branches e se caem dentro do intervalo selecionado e do `.text` declarado. Não resolve funções chamadas, memória, literal pools, tabelas de dados, relocations ou ABI.

## Inspeção A32 de chamadas e prólogos/epílogos

O inspetor seleciona somente a faixa indicada pelo mantenedor e reconhece um subconjunto adicional de instruções A32:

- `BL`: calcula o destino com `address + 8 + SignExtend(imm24 << 2)`, reporta LR=`address + 4` e trata a transferência como chamada candidata; não afirma a identidade da função chamada.
- `BLX` imediato: inclui o bit H no deslocamento, reporta estado de destino Thumb e retorno para o estado A32 chamador.
- `BX Rm` e `BLX Rm`: reporta transferência indireta; o valor de Rm não é conhecido e o alvo fica nulo. `BLX Rm` conserva o estado de retorno de acordo com o estado no qual a instrução foi inspecionada.
- `LDR Rt, [PC, #±imm12]` word, com `Rt != PC`: informa `address + 8 ± imm12`, largura de 4 bytes e eventual sobreposição com o intervalo. O valor do literal nunca é lido. `LDR PC` literal e casos fora do subconjunto permanecem desconhecidos.
- `STMDB sp!, {register-list}` e `LDMIA sp!, {register-list}`: identifica os padrões comuns de prólogo/epílogo ARM, lista registradores observados, efeito de memória e delta SP. Se `pc` é carregado da pilha, o relatório marca transferência indireta sem adivinhar o destino ou provar que o trecho é uma função completa.

Esses encodings são cobertos por fixtures sintéticas na suíte completa aprovada: [run 40200493912](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40200493912), 267 testes, matriz diferencial 96/96 e verificador de segurança PASS. Referências de formato: [BL/BLX immediate A32](https://mikhailarkhipov.github.io/ARM-doc/A32/bl_i.html) e [LDR literal](https://support.arm.com/documentation/ddi0487/md/-Part-F-The-AArch32-Instruction-Sets/-Chapter-F5-T32-and-A32-Base-Instruction-Set-Instruction-Descriptions/-F5-1-Alphabetical-list-of-T32-and-A32-base-instruction-set-instructions/-F5-1-74-LDR--literal-).

## A32 loads/stores por offset imediato ou registrador

O inspetor reconhece um subconjunto conservador de transfers A32 AL em instruções `LDR/STR` word/byte e no grupo extra `LDRH/STRH/LDRSB/LDRSH`. Os endereçamentos suportados incluem offset/pre-index, pre-index com writeback e post-index. Para word/byte, o offset pode ser imediato ou vir de registrador com shift imediato; para o grupo extra, o offset pode ser imediato split `imm4H:imm4L` ou um registrador simples sem shift.

O `memory_access` informa direção, largura, signedness, base, registrador de dado, offset, offset-reg/shift, modo de endereço e writeback. `offset_carry_input: c` é registrado para RRX. `runtime_effective_address_resolved: false` e `memory_value_read_by_inspector: false` são deliberados: nenhum valor de registrador ou memória é inventado ou lido. Loads para PC são marcados como saltos indiretos sem destino inventado.

Continuam desconhecidos: register-specified shift (bit 4), base/offset PC fora do literal coberto, LDRH/LDRSB/LDRSH literal, loads/stores não privilegiados (`P=0,W=1`), halfword/sign encodings não cobertos, alias imprevisível `Rn=Rt` com writeback e outras instruções não explicitamente reconhecidas. O tradutor C não recebe estas instruções; isso amplia somente a inspeção estática.

Esta classificação segue os campos P/U/B/W/L para transfers comuns e os encodings de extra load/store publicados pela Arm: [STR immediate A32](https://mikhailarkhipov.github.io/ARM-doc/A32/str_i.html), [LDRH immediate A32](https://support.arm.com/documentation/ddi0406/c/Application-Level-Architecture/Instruction-Details/Alphabetical-list-of-instructions/LDRH--immediate--ARM-) e [LDRSB immediate A32](https://kib.kiev.ua/x86docs/ARM/XML/2026-09/ISA_AArch32_xml_A_profile_2025-09_96-2025-09_ASL1/xhtml/ldrsb_i.html). A suíte integral mais recente passou no [run 40201786274](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40201786274), com 277 testes, matriz diferencial 96/96 e verificador de segurança PASS.

## Grafo estrutural de fluxo

O decodificador Thumb-16 também reconhece o grupo de processamento entre registradores completo de 16 opcodes: ANDS/EORS/LSLS/LSRS/ASRS/ADCS/SBCS/RORS/TST/RSBS/CMP/CMN/ORRS/MULS/BICS/MVNS. Os shifts por registrador usam Rs[7:0] como quantidade e a formatação do relatório preserva os dois operandos. A ferramenta não simula registradores nem infere valores em tempo de execução; a semântica C e os testes de NZCV pertencem à POC-002 sintética.

No grupo Thumb-1 data-processing register, os 16 opcodes agora são decodificados e formatados, incluindo shifts por registrador e MULS. Isso é cobertura sintática do grupo, não de todas as instruções Thumb-1/Thumb-2 nem prova de que qualquer intervalo selecionado seja código executável.



Cada relatório contém `control_flow`, um grafo candidato de blocos básicos construído a partir do intervalo explicitamente selecionado. Destinos de branches só viram arestas internas quando coincidem com o início de uma instrução descodificada no mesmo estado; branches condicionais têm arestas de tomada e não tomada; branches incondicionais não recebem uma aresta de fallthrough. Chamadas diretas são listadas como transferências candidatas com continuação possível após retorno, sem afirmar identidade do callee. Transferências indiretas ficam sem destino inventado.

Instruções desconhecidas encerram o bloco e não recebem sucessor presumido. Se um LDR literal aponta para dentro do intervalo selecionado, o grafo expõe a referência como possível dado e acrescenta aviso. A classificação é deliberadamente conservadora: não calcula valores de registradores, não prova alcançabilidade real, não descobre entradas de função e não resolve pools de literais.

Os blocos são hipóteses estruturais do trecho escolhido, não limites garantidos de funções. Antes de traduzir um bloco real, ainda é necessário confirmar que o início e o estado ARM/Thumb foram escolhidos corretamente e estabelecer um contrato de entrada/saída.

## Limites

A saída é uma anotação sintática de uma região, não código C executável nem prova de equivalência. Mesmo quando todos os encodings são reconhecidos, as POCs sintéticas têm uma ABI artificial e o estado real do jogo não foi modelado. O próximo marco precisa definir um contrato de função/entrada e comparar estado de registradores/flags com um oráculo independente antes de tentar compilar um trecho real em runtime.

Nenhum código do jogo foi usado na CI. Os testes usam ExHeaders, `.code`, endereços e instruções fabricados para testes.
