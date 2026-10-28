# POC-003 — transferência múltipla A32 com pilha limitada

## Estado

**Implementação experimental publicada, com validação sintética local em C11.** Isso não é parte de uma recompilação validada do Ultra Sun/Ultra Moon e não prova que funções reais sejam compatíveis.

## Objetivo

Estabelecer um primeiro modelo explícito de SP, LR, registradores gerais e memória de pilha para ARM A32, sem ampliar indevidamente a POC aritmética existente nem mudar sua ABI. A ferramenta emite C para uma sequência fixa de instruções suportadas; ela não interpreta instruções ARM em tempo de execução e não contém fallback de emulação ou JIT.

## Subconjunto suportado

- STMDB SP!, {reglist} com condição AL: decrementa o SP pela quantidade de palavras, grava os registradores listados em ordem crescente de número de registrador em endereços crescentes e atualiza SP depois de validar a transferência inteira.
- LDMIA SP!, {reglist} com condição AL: carrega os registradores listados em ordem crescente de número de registrador e só atualiza SP depois de validar a faixa inteira e preparar os valores.
- BX LR exato como terminador de sequência.
- `LDMIA SP!, {registros, PC}` em condição AL é aceito somente no final de uma sequência. O destino carregado para PC é exposto pelo parâmetro `guest_pc_out` da interface dedicada `a32_stack_transfer_entry_with_pc`; não é executado como salto nativo.
- A variante `translate_mixed_sequence` aceita também as formas AL não-S imediatas de `MOV`, `ADD` e `SUB` que o decodificador A32 existente reconhece em `r0–r3`. Essas instruções e as operações de pilha compartilham o mesmo vetor `r0–r14`, e cada instrução incrementa o orçamento de execução. Nenhuma outra família do decodificador geral é aceita por essa variante.

As listas `STMDB SP!` podem incluir r0–r12 e LR (r14), mas não SP nem PC. As listas `LDMIA SP!` podem incluir r0–r12 e LR; PC só é aceito no epílogo terminal dedicado. O modelo rejeita SP na lista com write-back, lista vazia, S-bit, condições diferentes de AL, outra base, outro modo de endereçamento, ausência de write-back e instruções fora do subconjunto. Na variante mista, os dados aritméticos se limitam a `MOV/ADD/SUB` imediatos sem S-bit em `r0–r3`; formas com flags e operandos de registrador não são aceitas. A presença de BX LR só termina a fixture: o endereço de retorno não é executado como um salto nativo.

## ABI sintética e memória

O C gerado recebe vetores de entrada/saída com 15 palavras, indexadas como r0–r14; portanto r13 é o SP e r14 é o LR. A região de memória é fornecida explicitamente por memory_bytes, memory_base e memory_size, com endereço final calculado em 64 bits para detectar overflow. A região deve ser não vazia e não pode ultrapassar o espaço de endereços de 32 bits.

O modelo exige alinhamento de quatro bytes para as transferências múltiplas. Antes de alterar memória, registradores ou SP, cada instrução valida a faixa completa. Se a transferência corrente falhar, ela não modifica o estado; transferências anteriores que terminaram com sucesso permanecem refletidas no resultado. As falhas são classificadas como:

| Status | Significado |
|---:|---|
| 0 | A sequência atingiu o terminador BX LR ou o epílogo terminal LDMIA-to-PC |
| 1 | Falha de memória, faixa inválida ou overflow de SP |
| 2 | Argumentos inválidos ou região de endereços inválida |
| 3 | SP desalinhado para uma transferência múltipla |

As instruções implementadas não alteram NZCV; o valor inicial validado é copiado para a saída. A política de falha atômica é o contrato seguro deste modelo sintético e não uma afirmação sobre os efeitos parciais de uma exceção de hardware real.

## Testes

O arquivo tests/test_a32_stack_transfer_poc.py cobre a decodificação e as rejeições explícitas, write-back, ordem de registradores, load/store little-endian, restauração de SP/LR, preservação de NZCV, falha de memória, alinhamento, overflow de faixa e preservação do estado em uma falha depois de uma transferência anterior bem-sucedida. Quando há compilador disponível, os testes compilam o C gerado com avisos tratados como erros e executam os binários. A fixture de round-trip e a falha por faixa também são exercitadas no pipeline nativo `tools/run_native_poc_pipeline.py`, que é executado pelo CTest. O gerador `tools/generate_native_abi_fixtures.py` também cria uma fixture A32 para a fronteira C/C++ versão 4. Ela usa `PokeNativeA32StackCall` e `PokeNativeA32StackResult`, cada um com 15 palavras para `r0–r14`; a ABI genérica existente, de oito registradores, permanece inalterada. O host C++ cobre round-trip, memória, falha por faixa, alinhamento e rejeição de versão.

Execute os testes dessa POC com:

    python -m unittest discover -s tests -p 'test_a32_stack_transfer_poc.py' -v

## Limitações e próximo passo

Esta é uma prova separada e limitada, não um tradutor A32 geral. Ainda não cobre LDM/STM com outras bases ou modos, flags S, retornos Thumb `POP {PC}`, desvios indiretos comuns, ABI completa do jogo, mapa de memória do 3DS, funções reais ou serviços do sistema. A POC aritmética A32 original continua com seu subconjunto e suas limitações próprias.

A POC participa agora de três níveis de teste: testes de tradução, pipeline C11 nativo e fronteira sintética C/C++ versionada. O teste de estado compartilhado intercala `MOV/ADD` com transferências de pilha e testa os epílogos A32 `LDMIA SP!, {registros, PC}` emitindo o destino convidado sem salto nativo. A suíte completa de 430 testes passou no [workflow #40609135281](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40609135281), e a pipeline C/C++ nativa passou em Linux e Windows no [workflow #40609135323](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40609135323). O próximo passo é expandir essa composição para mais operações e registradores sem misturar as APIs sintéticas com a ABI real do jogo. A integração atual ainda não traduz uma função real. Só depois de validar o build Linux/Windows deve ser selecionada uma função real autorizada, com estado ARM confirmado e contrato de efeitos, para uma tentativa local de recompilação. Nenhum endereço, byte, desassemblagem ou recurso do jogo deve ser publicado como evidência.
