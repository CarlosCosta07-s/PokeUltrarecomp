# Censo agregado de código — Pokémon Ultra Sun

**Data da inspeção:** 27 de outubro de 2026  
**Execução de referência:** [GitHub Actions #40582007887](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40582007887)  
**Escopo:** métricas agregadas geradas no runner temporário; nenhum endereço, byte de instrução, desassemblagem ou recurso do jogo é publicado.

## Resultado verificado

A execução terminou com sucesso. O contêiner CCI e o layout extraído foram validados, e o identificador de conteúdo foi classificado como correspondendo ao alvo-base Ultra Sun. O segmento executável `.text` validado tinha **4.954.608 bytes**. A imagem e os dados derivados permaneceram no armazenamento temporário do runner; a execução não produziu artefatos.

### Censo do Ghidra

| Métrica agregada | Contagem |
|---|---:|
| Entradas de função reconhecidas dentro de `.text` | 17.592 |
| Corpos reconhecidos de até 32 bytes | 2.949 |
| Corpos reconhecidos de até 64 bytes | 6.058 |
| Corpos reconhecidos de até 128 bytes | 9.953 |
| Corpos classificados como funções-leaf | 4.262 |
| Funções-leaf de até 32 bytes | 1.868 |
| Funções-leaf de até 64 bytes | 2.802 |
| Funções-leaf de até 128 bytes | 3.554 |
| Corpos com instrução semelhante a retorno | 14.378 |
| Funções-leaf de até 64 bytes com retorno semelhante | 2.154 |
| Instruções nos corpos classificados como leaf de até 64 bytes | 18.925 |
| Corpos excluídos por cruzarem os limites de `.text` | 0 |

Esses números descrevem o resultado da análise automática do Ghidra, não uma prova independente de que cada função ou limite está correto.

### Censo heurístico de prólogos e retornos

| Padrão de entrada candidato | Ocorrências |
|---|---:|
| ARM: `PUSH` / `STMDB SP!` | 17.596 |
| ARM: `SUB SP, #imediato` | 5.490 |
| Thumb: `PUSH` | 1.311 |
| Thumb: `SUB SP, #imediato` | 622 |
| **Total de locais candidatos** | **25.019** |

Em uma varredura linear limitada a 512 bytes e 96 instruções por candidato, **12.752** locais chegaram a uma instrução semelhante a retorno: 12.606 em estado ARM e 146 em Thumb. **3.803** chegaram a tal instrução em até 16 instruções. As terminações classificadas nessa varredura foram:

| Forma de retorno aparente | Contagem |
|---|---:|
| `POP {PC}` | 12.317 |
| `BX LR` | 431 |
| `MOV PC, LR` | 3 |
| `LDM ... {PC}` usando SP | 1 |

A análise é propositalmente conservadora quanto ao que publica, mas é **heurística**: o segmento pode conter dados além de código; uma varredura linear não demonstra alcançabilidade, não segue todos os desvios e não confirma limites de função. Os locais candidatos não devem ser tratados como funções prontas para recompilação.

### Mnemonics agregados em corpos leaf curtos

O Ghidra classificou os seguintes mnemonics com maior frequência nos corpos que identificou como funções-leaf de até 64 bytes. A lista é um histograma desse subconjunto, **não** uma contagem de todo o segmento e **não** mede diretamente a cobertura do tradutor.

| Mnemonic | Ocorrências | Mnemonic | Ocorrências |
|---|---:|---|---:|
| `ldr` | 2.948 | `bx` | 1.898 |
| `str` | 1.712 | `cpy` | 1.706 |
| `mov` | 1.384 | `cmp` | 1.207 |
| `add` | 1.052 | `strb` | 584 |
| `ldmia` | 511 | `stmdb` | 451 |
| `ldrb` | 401 | `beq` | 368 |
| `and` | 294 | `bne` | 268 |
| `ldrh` | 235 | `movne` | 196 |
| `swi` | 186 | `b` | 182 |
| `mrc` | 158 | `stmia` | 154 |

Mnemonics como `cpy` podem ser aliases exibidos pelo desassemblador. A presença de `swi` ou `mrc` também reforça que traduzir instruções isoladas não basta: o runtime terá de tratar ou rejeitar explicitamente chamadas de sistema e operações de coprocessador relevantes.

## O que isso significa para o tradutor atual

O censo confirma que a próxima etapa precisa aproximar o modelo experimental da ABI ARM, não apenas adicionar operadores aritméticos aleatórios. A POC A32 atual continua deliberadamente limitada:

- o modelo de registradores é restrito a `r0–r3`;
- os acessos de memória cobertos são formas escalares pré-indexadas com imediato, sem write-back nem offset em registrador;
- as transferências A32 `STMDB SP!` e `LDMIA SP!` são cobertas apenas pela POC-003 experimental, com memória sintética delimitada;
- a POC-003 agora permite `BX LR` ou o epílogo terminal `LDMIA SP!, {registros, PC}`, retornando o valor de PC como destino convidado explícito;
- a região de memória de teste é sintética e delimitada, não o mapa de memória real do 3DS.

Por isso, a contagem de entradas do Ghidra não indica quantas funções já podem ser recompiladas. O tradutor ainda não recebeu uma função real selecionada e validada semanticamente.

## Execuções posteriores e limitações operacionais

A tentativa posterior de repetir a ingestão, [workflow #40594739458](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40594739458), falhou antes da análise porque o Google Drive limitou o download. Nenhum resultado dessa tentativa deve ser contado como uma nova inspeção do código.

A versão atual de `tools/remote_3ds_intake.py` faz triagem agregada dos candidatos privados do Ghidra. Além do tradutor ARM geral, ela tenta a POC-003 mista em sequências A32 com `MOV/ADD/SUB` imediatos e `STMDB/LDMIA SP!`; o extrator Ghidra também admite epílogos terminais `LDMIA SP!, {registros, PC}`. O destino de retorno é devolvido como dado convidado explícito, nunca como salto para o host, e a triagem conta esses casos separadamente. O teste `test_private_real_candidate_screen_uses_mixed_a32_stack_translator` verifica esse caminho com uma fixture sintética; ele não é evidência de compatibilidade com o jogo real. A execução bem-sucedida #40582007887 não incluiu essa nova triagem e a tentativa #40594739458 parou no download antes que ela pudesse rodar. Portanto, ainda precisamos de uma nova ingestão com a imagem real para obter as contagens reais e selecionar um candidato para análise semântica.

Não há artefatos da execução de referência nem persistência do segmento de código entre runners; uma nova análise real precisa executar de novo a ingestão no próprio workflow.

## Próxima tarefa técnica recomendada

1. Definir e testar um modelo A32 mais fiel de registradores de entrada/saída e uma região de pilha limitada, com contratos claros para `SP`, `LR`, flags e falhas.
2. Depois disso, implementar uma família pequena de transferências múltiplas A32 — começando por formas específicas de `STMDB SP!` e `LDMIA SP!` — com ordem de registradores, write-back, alinhamento, limites, overflow e preservação do estado em falhas testados.
3. Validar com uma função real autorizada o contrato de retorno A32 via `LDMIA SP!, {registros, PC}`; manter retornos Thumb `POP {PC}` separados, sem supor que os dois estados tenham semântica idêntica.
4. Executar os testes sintéticos específicos e a suíte completa, validar Linux/Windows e só então inspecionar candidatos reais de modo local/temporário. A triagem real posterior deve publicar apenas contagens agregadas e jamais bytes, endereços ou desassemblagens.

**Estado final desta inspeção:** censo agregado real concluído; nenhuma função do jogo foi recompilada ou executada.