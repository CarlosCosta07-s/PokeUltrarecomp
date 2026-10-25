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
- Informa os destinos calculados de branches e se caem dentro do intervalo selecionado e do `.text` declarado. Não resolve funções chamadas, memória, literal pools, tabelas de dados, relocations ou ABI.

## Limites

A saída é uma anotação sintática de uma região, não código C executável nem prova de equivalência. Mesmo quando todos os encodings são reconhecidos, as POCs sintéticas têm uma ABI artificial e o estado real do jogo não foi modelado. O próximo marco precisa definir um contrato de função/entrada e comparar estado de registradores/flags com um oráculo independente antes de tentar compilar um trecho real em runtime.

Nenhum código do jogo foi usado na CI. Os testes usam ExHeaders, `.code`, endereços e instruções fabricados para testes.
