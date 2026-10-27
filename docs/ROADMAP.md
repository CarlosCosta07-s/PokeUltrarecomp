# Roadmap técnico

Este roadmap é um plano de trabalho, não uma declaração de funcionalidades implementadas. Nenhuma fase deve ser marcada como concluída sem evidências revisáveis. O critério de aceitação é a condição mínima para encerrar cada fase; descobertas podem exigir tarefas adicionais.

A direção técnica está registrada em [NATIVE_PORT_DIRECTION.md](NATIVE_PORT_DIRECTION.md): runtime próprio C++20, C gerado compilado nativamente, SDL3 e Vulkan, Windows/Linux x86-64 como primeiros alvos, sem emulação, interpretação, JIT ou fallback interpretado. A arquitetura ainda não está implementada. A prioridade funcional precede otimizações de desempenho.

## Fase 1 — Organização e auditoria

**Estado:** documentação, auditoria inicial e verificador local de segurança publicados; a verificação integral da árvore da `main` e a revisão final de governança continuam pendentes. A decisão sobre o LICENSE preexistente está registrada no [issue #1](https://github.com/CarlosCosta07-s/PokeUltrarecomp/issues/1).

**Tarefas**
- [ ] Manter README, arquitetura, regras de contribuição, segurança e avisos legais consistentes.
- [ ] Registrar os commits e documentos de cada projeto de referência em [AUDIT.md](AUDIT.md).
- [ ] Separar fatos publicados, evidências autorrelatadas, hipóteses e perguntas abertas.
- [x] Adicionar verificador local sem dependências para caminhos sensíveis e links Markdown, cobrindo blobs do índice Git e versões da pasta de trabalho.
- [ ] Confirmar que não há conteúdo de jogo, segredos, chaves ou artefatos de build no Git.
- [ ] Revisar o arquivo LICENSE preexistente, cuja procedência e abrangência não estão documentadas ([issue #1](https://github.com/CarlosCosta07-s/PokeUltrarecomp/issues/1)).

**Dependências:** nenhuma.

**Critério de conclusão:** todos os documentos básicos existem; os quatro projetos e seus commits consultados estão registrados; a licença preexistente tem uma decisão explícita do mantenedor; nenhum marco técnico é anunciado sem evidência.

## Fase 2 — Verificação de licenças e dependências

**Tarefas**
- [ ] Confirmar por escrito o estado de licença de cada fonte candidata e de cada subcomponente.
- [ ] Revisar arquivos LICENSE, cabeçalhos de copyright, metadados, dependências transitivas e atribuições.
- [ ] Verificar separadamente licença de código, licença de ferramentas e direitos sobre dados de jogos.
- [ ] Atualizar [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) com commit, origem e modificações de qualquer dependência aprovada.
- [ ] Não reutilizar fontes cujo direito de redistribuição esteja ausente ou ambíguo.

**Dependências:** fase 1.

**Critério de conclusão:** cada componente usado na prova de conceito tem licença e procedência verificadas; obrigações de atribuição e distribuição estão documentadas; itens não liberados permanecem apenas referências externas.

## Fase 3 — Preparação do ambiente Windows/WSL

**Tarefas**
- [ ] Escolher e registrar versões de Windows, WSL/distribuição Linux, Git, Rust, compilador C/C++, CMake/Ninja e ferramentas auxiliares conforme a prova de conceito.
- [ ] Evitar instalar toolchains ou clonar projetos inteiros antes de definir o teste necessário.
- [ ] Documentar opções de instalação oficiais, hashes de downloads relevantes e comandos de diagnóstico.
- [ ] Manter entradas locais e diretórios temporários fora do repositório.
- [ ] Executar um diagnóstico de compilador e um teste trivial independente de dados proprietários.

**Dependências:** fases 1 e 2.

**Critério de conclusão:** um ambiente limpo reproduz o diagnóstico e o teste trivial; versões e resultados estão registrados em BUILD_NOTES.md; nenhum conteúdo proprietário é necessário.

## Fase 4 — Reproduzir um teste de referência documentado

**Estado atual:** procedimento PowerShell local preparado em [REFERENCE_TEST_001.md](REFERENCE_TEST_001.md); execução e resultado continuam pendentes. Este projeto não depende de GitHub Actions.

**Tarefas**
- [ ] Selecionar uma prova de teste sintética ou um teste de unidade publicado por uma ferramenta de referência que não exija ROM/dump.
- [ ] Preferir um teste de compilação, verificação de instruções reconstruídas contra um intérprete ou teste do runtime de PC com fixtures sintéticas.
- [ ] Fixar o commit exato da ferramenta e as versões de compilador/dependências.
- [ ] Registrar comandos, saída completa relevante, código de saída e resultado em BUILD_NOTES.md.
- [ ] Se o teste escolhido exigir arquivo de jogo local, avaliar primeiro um caso sintético alternativo. Não enviar a entrada, sua extração nem saída derivada ao Git/CI.

**Dependências:** fases 2 e 3.

**Critério de conclusão:** outra pessoa pode reproduzir o mesmo teste com ferramentas permitidas e sem arquivos proprietários; o resultado deste repositório é explicitamente identificado como sucesso, falha ou inconclusivo.

## Fase 5 — Definir a primeira prova de conceito

**Preparação experimental:** a POC-001 traduz fixtures ARM A32 sintéticas para C. O tradutor aceita `ADDS`, `SUBS`, `CMN` e `CMP` imediatos, `B` sob as 14 condições padrão, predicação das instruções de dados suportadas e desvios para trás/autoalvo somente com orçamento de 1 a 100.000 instruções. O núcleo POC-001 mantém 92 testes; depois de adicionar o inspetor de alvo, a suíte integral passou em **106 testes aprovados, zero falhas e zero ignorados** no commit `85bbe6eb91cc53ee596c674b551bc74ea5df4bb3`. Sintaxe Python, matriz diferencial 96/96 e verificador de segurança também passaram; o último analisou 33 caminhos indexados. [Registro da execução](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40157669355). A primeira tentativa anterior encontrou um erro no teste C de `CMP` condicional; ele foi corrigido antes da execução aprovada. O clone local continua sem resolver DNS, mas o runner hospedado fez checkout completo da `main`. O teste interno não usa emulador e não prova compatibilidade com Ultra Sun/Ultra Moon. O projeto ainda não constitui um runtime de jogo.

**Tarefas**
- [ ] Escolher apenas uma unidade pequena, com limite de escopo e um resultado observável.
- [ ] Definir entrada sintética permitida, saída esperada, dependências e como demonstrar a origem do código.
- [ ] Decidir se a prova testa recompilação de uma função, camada de abstração ou comportamento de um runtime host.
- [ ] Separar compilação da ferramenta, compilação de código reconstruído e execução no host.
- [ ] Criar testes automatizáveis que não necessitem de dumps ou recursos extraídos.

**Dependências:** fase 4 aprovada e licenças da ferramenta confirmadas.

**Critério de conclusão:** existe uma especificação curta aprovada com comando reproduzível, teste de sucesso, teste negativo e evidência que distingue a prova de conceito de um jogo funcional.

## Fase 5A — Intake dos executáveis de Ultra Sun / Ultra Moon

**Estado:** ferramenta local de preflight implementada e coberta por fixtures sintéticas. Lê o Program ID no ACI do ExHeader, confere o alvo e calcula os offsets no `.code` com o layout page-padded declarado. Em 27/10/2026, uma imagem CCI real de Ultra Sun foi processada em armazenamento temporário no workflow [#40567703483](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40567703483): extração/layout passaram e nenhum arquivo do jogo foi publicado como artifact. Isso confirma apenas o pré-processamento estrutural dessa entrada, não a autenticidade/revisão exata nem uma função recompilada.

**Tarefas desta etapa**
- [x] Adicionar perfis distintos de Ultra Sun e Ultra Moon, com IDs-base/atualização conhecidos e política de entradas locais.
- [x] Ler SCI e Program ID do ACI, validar o alvo embutido, endereços, páginas, tamanhos, sobreposição e comprimento exato do `.code` page-padded; reportar offsets dos segmentos.
- [x] Emitir JSON com SHA-256 local e metadados sem copiar bytes ou caminhos absolutos.
- [x] Expor candidatos de variante por tamanho de `.code` a partir de referência comunitária; o resultado é explicitamente heurístico e não autentica a revisão.
- [x] Adicionar testes sintéticos de sucesso, falha, incompatibilidade de título e CLI.
- [x] Executar um preflight para uma imagem CCI autorizada de Ultra Sun em runner temporário, com resultado redigido e sem artifact de jogo (workflow [#40567703483](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40567703483)). A identidade exata da revisão ainda não foi comprovada.
- [x] Executar uma contagem heurística agregada de padrões comuns de prólogo no segmento `.text` de Ultra Sun: 25.019 ocorrências candidatas. Isso não equivale ao número de funções e pode incluir dados/padrões coincidentes.
- [x] Refinar a triagem com Capstone: 12.752 candidatos alcançaram linearmente um retorno comum dentro de 512 bytes/96 instruções; 3.803 chegaram ao retorno em até 16 instruções. A leitura não segue o grafo de controle e esses totais não representam funções validadas.
- [x] Criar um script Ghidra headless que emite apenas contagens agregadas de funções detectadas, tamanhos, folhas e mnemônicos comuns; parser Python de relatório falha fechado se houver campos de endereço/desassemblagem. Execução Ghidra com a imagem real ainda pendente até validação do workflow.
- [x] Criar um inventário heurístico agregado de padrões comuns de prólogo ARM/Thumb, com saída sanitizada e testes sintéticos; isso não substitui a identificação manual de funções reais.
- [x] Implementar a leitura do Program ID no cabeçalho NCCH da partição selecionada em contêineres NCSD (.3ds/.cci), com validação de limites, magia e partição; comparar o Title ID encontrado ao perfil conhecido, sem publicar o identificador literal. A validação com CCI real está em execução; .cia/TMD permanece pendente.
- [ ] Validar separadamente uma entrada autorizada de Ultra Moon.
- [ ] Identificar e confirmar manualmente limites/estados de funções ARM/Thumb reais, sem reutilizar fontes cuja licença não está confirmada.

**Critério de conclusão:** preflight reproduzível em entradas locais dos dois jogos, revisão exata identificada e nenhuma entrada/extração/saída derivada publicada. A etapa atual ainda não é desassemblagem nem recompilação.

## Fase 5B — POC-002: subconjunto Thumb-16

**Estado:** tradutor sintético implementado e validado no checkout completo da `main`: suíte combinada de 136 testes aprovada, sem falhas nem testes ignorados. A parte que conecta intervalos identificados nos executáveis reais aos tradutores permanece pendente.

**Cobertura atual**
- [x] Decodificar `MOVS`, `ADDS`, `SUBS` e `CMP` imediatos.
- [x] Traduzir branches incondicionais e condicionais EQ..LE com offsets Thumb relativos ao PC (endereço atual + 4).
- [x] Modelar flags NZCV, entrada explícita, sequência com `BX LR` e limite de execução para laços.
- [x] Testar a fixture nativa e as 224 combinações de condição/estado NZCV contra tabela independente.
- [x] Executar a suíte integral, a matriz diferencial e o verificador de segurança no runner hospedado.
- [ ] Conectar a tradução somente a intervalos de código identificados por análise de fluxo/estado ARM-Thumb; não fazer linear sweep indiscriminado em `.text`.

**Critério da POC sintética:** cumprido para a sequência explicitamente fornecida e o subconjunto listado. A integração aos jogos continua aberta até haver descoberta de funções, identificação de estado ARM/Thumb, análise de dados embutidos e verificação diferencial independente.

## Fase 5D — Inspeção de intervalo de código escolhido pelo mantenedor

**Estado:** inspeção sintática de intervalos ARM/Thumb, grafo candidato de controle e sumário conservador de efeitos. A cobertura A32 inclui chamadas/literais, transferências de múltiplos registradores, LDR/STR word/byte com offset imediato ou registrador, o grupo extra LDRH/STRH/LDRSB/LDRSH, processamento de registradores com shift imediato e cargas/armazenamentos condicionais EQ..LE. A suíte integral passou em **286 testes**, matriz diferencial 96/96 e verificador de segurança no [run 40216237581](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40216237581). Nenhum `.code` real foi lido. A próxima dependência real é o mantenedor escolher localmente uma região autorizada e confirmar endereço inicial/estado ARM-Thumb; não se deve varrer `.text` indiscriminadamente.

**Tarefas**
- [x] Mapear endereço virtual para offset de `.code` descomprimido a partir do layout do ExHeader validado.
- [x] Exigir estado ARM/Thumb e contagem explícitos; rejeitar intervalos fora do payload `.text` e endereços desalinhados.
- [x] Adicionar modo de inspeção parcial que registra encodings desconhecidos sem mnemônicos inventados e agrupa prefixos Thumb-2 de 32 bits para preservar alinhamento.
- [x] Decodificar somente o subconjunto reconhecido e falhar de forma clara ao encontrar instrução não suportada.
- [x] Informar destinos de branch e se caem dentro do intervalo e do `.text` declarado.
- [x] Decodificar e formatar load/store Thumb-1 por registrador, imediato e SP; registrar largura/acesso, offsets escalados e extensão de sinal sem ler a memória.
- [x] Decodificar LDMIA/STMIA, rejeitar lista vazia, formatar listas de registradores e reportar transfer_count/total_bytes/writeback sem ler memória.
- [x] Decodificar ADR e ADD/SUB SP com alvo PC alinhado e delta de pilha, mantendo o cálculo de valores dinâmicos não resolvido.
- [x] Decodificar chamadas A32 `BL`/`BLX` imediato e `BX Rm`/`BLX Rm` sem inventar destino de registrador.
- [x] Decodificar A32 `LDR` literal word PC-relativo, reportando o endereço sem ler o valor.
- [x] Identificar formas comuns de prólogo/epílogo `STMDB sp!`/`LDMIA sp!`, efeito de stack/memória e PC carregado como fluxo indireto.
- [x] Decodificar A32 LDR/STR word/byte com offset imediato, modos pre/post-index e writeback; registrar efeitos sem resolver endereço efetivo ou ler memória.
- [x] Decodificar A32 LDR/STR word/byte por offset em registrador com shifts imediatos, incluindo RRX como leitura de carry.
- [x] Decodificar LDRH/STRH/LDRSB/LDRSH com offset imediato split e offset em registrador sem shift.
- [ ] Integrar o resultado a uma seleção de intervalo candidato que exija confirmação do mantenedor do endereço inicial e do estado ARM/Thumb.
- [x] Adicionar inspeção sintática A32 para AND/EOR/SUB/RSB/ADD/ORR/MOV/BIC/MVN e TST/TEQ/CMP/CMN com shift imediato, incluindo condições EQ..LE e sumário dos flags de condição; manter shifts controlados por registrador, operandos PC e condição 0xF fora do subconjunto.
- [x] Executar testes sintéticos na suíte completa; validação mais recente: 283 testes no [run 40203189860](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40203189860), incluindo transferências de memória A32 e processamento de registradores com shift imediato e predicação.
- [x] Adicionar inspeção condicional EQ..LE para LDR/STR word/byte e formas halfword/signed-load já reconhecidas; registrar condição lida e efeitos de memória sem ler valores.
- [ ] Usar um intervalo local autorizado escolhido pelo mantenedor após confirmar o estado ARM/Thumb, sem compartilhar bytes ou relatório derivado.
- [ ] Definir e validar contrato de entrada, registradores e flags antes de propor emissão C ou execução.
- [x] Definir o formato de contrato de função candidata e um validador estático contra os efeitos observados (`tools/check_function_contract.py`, [guia](FUNCTION_CONTRACT.md)); falha fechada e sem declarar validação. O oráculo independente e a validação em entrada local autorizada continuam pendentes.

**Critério de conclusão:** anotação sintática reproduzível para intervalo selecionado, sem incluir entradas ou extrações na CI. Isso não prova equivalência semântica nem runtime de jogo.

## Fase 5E — Grafo estrutural de fluxo ARM/Thumb

**Estado:** análise candidata integrada ao relatório de intervalo explícito; testes usam apenas instruções e metadados sintéticos.

- [x] Formar blocos básicos candidatos por entrada explícita, destinos de branches conhecidos e instruções de transferência de controle.
- [x] Diferenciar taken/fallthrough de branches condicionais e suprimir fallthrough de branches incondicionais.
- [x] Registrar chamadas diretas e indiretas sem inventar destino de execução ou identidade de função.
- [x] Tratar instruções desconhecidas como barreiras e sinalizar LDR literal que se sobrepõe ao intervalo examinado.
- [x] Ampliar POC-002 com ADD/SUB Thumb-1 de três operandos, tanto registrador quanto imediato de 3 bits, com NZCV validado em C nativo.
- [x] Adicionar LSL/LSR/ASR Thumb-1 com imediato, incluindo as regras de imm5=0 e carry validadas por C nativo.
- [x] Completar a tabela dos 16 opcodes do grupo Thumb-1 de processamento de registradores: ANDS/EORS/LSLS/LSRS/ASRS/ADCS/SBCS/RORS/TST/RSBS/CMP/CMN/ORRS/MULS/BICS/MVNS, com testes nativos de resultado/flags e cobertura do inspetor.
- [x] Adicionar RSBS Rdn,Rm,#0 com testes nativos de negação e overflow assinado.
- [x] Implementar ADCS/SBCS Thumb-1 com carry/borrow de entrada, carry de saída e testes nativos compilados.
- [x] Completar LSLS/LSRS/ASRS/RORS por registrador, testar valores de shift 0/32/>32 e registrar a semântica no inspetor de intervalos.
- [ ] Usar entrada local autorizada de Ultra Sun ou Ultra Moon com endereço/estado verificados; revisar o grafo localmente sem publicar bytes nem relatório derivado.
- [ ] Definir o contrato de uma função candidata e um oráculo independente antes de converter código real em C.

**Limite:** o grafo só descreve o trecho escolhido e não prova que ele começa numa função, não resolve funções chamadas, e não modela registradores/memória. Sem uma entrada local autorizada, não há evidência de que algum caminho real dos jogos tenha sido identificado.

## Fase 5F — Efeitos observados de registradores e flags

**Estado:** sumário sintático conservador implementado e validado como parte dos 271 testes do [run 40200917080](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40200917080). Não é análise de vivacidade, execução simbólica ou inferência de ABI.

- [x] Relatar leituras/escritas observadas de registradores para o subconjunto conhecido de ARM A32/Thumb.
- [x] Relatar leitura/escrita de NZCV para condições, aritmética, comparações e operações Thumb suportadas.
- [x] Distinguir load/store e transferências de stack; representar chamadas e encodings desconhecidos como efeitos incompletos.
- [x] Agregar efeitos observados no relatório de intervalo sem afirmar contrato de retorno ou preservação de registradores.
- [ ] Validar as anotações contra uma referência ARM independente e ampliar o subconjunto somente com fixtures verificadas.
- [ ] Aplicar o relatório a uma faixa local autorizada, escolhida e revisada pelo mantenedor; não publicar bytes ou relatórios derivados.

**Critério:** o relatório informa o que o decodificador atual permite inferir sintaticamente e identifica explicitamente onde não é seguro concluir. Não gera C nem demonstra equivalência semântica.

## Fase 6 — Pipeline de recompilação nativa sem fallback

**Estado:** a região de memória Thumb e as operações `LDMIA/STMIA` estão integradas à ABI C versionada usada pelo host C++20. O [workflow nativo #40444774067](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40444774067), commit `0f78853b0b30c80725304840f6988f411b881ef2`, passou 4/4 testes CTest em Windows/MSVC e Linux/GCC. O host C++ chama as funções geradas para múltiplas transferências e para `LDMIA` com a base na lista, verificando ordem, write-back, bytes de memória, status guest de falhas por faixa/alinhamento e preservação da região após erro. A suíte Python passou em 327 testes no [workflow #40444774027](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40444774027). A evidência é sintética: não há runtime de jogo, função real recompilada nem gameplay validado.

**Tarefas**
- [x] Adicionar `CMakeLists.txt` com C11/C++20, CTest e alvo `verify` para coordenar smoke test, testes Python e verificador de segurança.
- [x] Validar a orquestração CMake + Ninja em Windows e Linux x86-64; os três testes CTest passaram em cada plataforma no [workflow #40441326568](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40441326568).
- [x] Adicionar um smoke test de ponta a ponta para fixtures sintéticas A32 e Thumb: tradutor → C gerado → compilador nativo → execução do binário.
- [x] Adicionar uma ABI C versionada entre as funções geradas para teste e um host C++20, com rejeição de argumentos/versionamento inválidos sem alteração parcial de resultados.
- [x] Integrar o host C++20 e as unidades C geradas ao build CMake; o job Windows aprovou os quatro testes CTest no workflow #40442412186.
- [x] Confirmar os quatro testes CTest da integração C/C++20 tanto em Windows quanto em Linux: [workflow #40442604997](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40442604997).
- [x] Validar resultados esperados, estado de registradores/flags e orçamento de instruções no processo nativo.
- [x] Cobrir inputs negativos: registrador ARM fora do subconjunto e operação de memória Thumb sem modelo de memória devem falhar explicitamente.
- [x] Adicionar um workflow de CI para executar o smoke test em Windows e Linux sem arquivos de jogo.
- [x] Confirmar execuções aprovadas do workflow em ambos os sistemas; corrigir qualquer falha antes de prosseguir.
- [ ] Unificar/estender a interface para cobrir regressões de decodificação, fluxo de controle, limites, contratos e falhas do compilador, mantendo um oráculo independente baseado na especificação.
- [x] Implementar um modelo de memória guest limitado para fixtures sintéticas e emitir loads/stores nativos para o subconjunto explicitamente aceito; validar limites, alinhamento, extensão de sinal e ausência de escrita parcial em erro no [workflow #40443547298](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443547298).
- [x] Expor base/tamanho/buffer de memória através de `PokeNativeMemory` na ABI C versionada e chamar a fixture C a partir do host C++20; testar status guest de falha e rejeição atômica de contratos inválidos no [workflow #40443861507](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443861507).
- [x] Implementar o subconjunto Thumb `LDMIA/STMIA` na região guest limitada, verificando todo o intervalo antes da transferência, ordem crescente dos registradores, write-back e a regra de `LDMIA` para base contida na lista; rejeitar `STMIA` com base na lista. Validado em [workflow #40444392587](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40444392587).
- [x] Expor `LDMIA/STMIA` e `LDMIA` com base na lista pela ABI C versionada; o host C++20 testa resultado/write-back, memória, falhas guest e integridade em erro no [workflow #40444774067](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40444774067).
- [ ] Decidir a política de alinhamento completa e continuar expandindo apenas após teste independente; manter `LDR` literal, acessos SP-relativos, `PUSH/POP` e demais instruções de memória não cobertas explicitamente como recusadas.
- [ ] Fazer com que toda instrução sem suporte, estado ARM/Thumb incerto e transferência não resolvida interrompam a tradução; nunca usar fallback interpretado.

**Dependências:** fases 2 e 3; as demonstrações sintéticas existentes da fase 5 são o ponto de partida.

**Critério de conclusão:** pipeline nativo reproduzível aprovado em ambos os sistemas operacionais, com resultados esperados, testes negativos e logs verificáveis. Isso ainda não conta como execução do jogo.

## Fase 7 — Primeiro alvo real recompilado

**Objetivo:** provar a transição de análise estática para execução nativa de uma função real antes de ampliar o runtime ou trabalhar em desempenho.

**Tarefas**
- [ ] Em ambiente local do mantenedor, selecionar uma entrada autorizada e uma função candidata cuja identidade, limites e estado ARM/Thumb sejam confirmados.
- [ ] Registrar o contrato da função: registradores e flags, stack, chamadas, memória, retorno, endereços e dependências.
- [ ] Ampliar a cobertura do tradutor somente conforme as instruções realmente observadas, cada uma com testes positivos/negativos e validação independente.
- [ ] Gerar C, compilar para código nativo e validar os efeitos observáveis da função sem emulador nem interpretador.
- [ ] Manter o código e os relatórios derivados de entradas proprietárias fora do Git e da CI; publicar apenas resultados redigidos e reproduzíveis.
- [ ] Registrar todo opcode, chamada, módulo, relocação ou contrato ainda não suportado; não declarar a função válida quando algum efeito relevante permanece desconhecido.

**Dependências:** fase 6 aprovada e entrada local permitida do mantenedor.

**Critério de conclusão:** pelo menos uma função real é recompilada, ligada e exercitada como código nativo com contrato e evidência revisáveis. Um resultado sintético não satisfaz este critério.

## Fase 8 — Runtime nativo e serviços de PC

**Tarefas**
- [ ] Criar interfaces C++20 de runtime apenas para os serviços comprovadamente requeridos pela primeira função/caminho real.
- [ ] Implementar memória, relógio, sincronização, arquivos e módulos conforme os contratos observados; definir a política de erro e encerramento.
- [ ] Adotar SDL3 para janela, teclado, controles e áudio, registrando a versão e atualizando os avisos/licenças antes da incorporação.
- [ ] Implementar o caminho gráfico nativo com Vulkan por operações de PC; não modelar uma GPU PICA200 nem interpretar listas de comandos de GPU.
- [ ] Testar cada interface com dados sintéticos, casos de falha e recuperação; confirmar que a saída não exige intérprete/JIT/emulador.
- [ ] Testar salvamento em diretório externo com escrita atômica, corrupção simulada, backup e recuperação.

**Dependências:** fases 6 e 7; código nativo funcional e os contratos do primeiro alvo real.

**Critério de conclusão:** os serviços que bloqueiam o primeiro caminho real estão implementados e testados no host Windows/Linux. Serviços ainda não implementados continuam explícitos como bloqueadores.

## Fase 9 — Primeiro caminho de jogo, estabilidade e desempenho posterior

**Prioridade:** obter um caminho real de execução antes de medir e otimizar desempenho. Não exigir FPS alto para considerar o primeiro passo funcional, mas não confundir uma inicialização isolada com jogabilidade.

**Tarefas**
- [ ] Ligar as funções recompiladas e os serviços nativos necessários ao primeiro caminho de jogo.
- [ ] Validar inicialização, um trecho observável de progressão, entrada, gráficos, áudio e salvamento conforme o caminho implementado.
- [ ] Repetir ciclos de inicialização/encerramento, perda de foco, remoção de dispositivos, erro de arquivo e falhas de serviço.
- [ ] Corrigir corrupção de estado, deadlocks, vazamentos e falhas que impeçam a execução confiável antes de ampliar a cobertura.
- [ ] Só depois de existir execução funcional, medir CPU/GPU, memória e tempos de quadro com ambiente documentado e definir o trabalho de otimização.
- [ ] Informar o que realmente funciona e quais caminhos continuam não suportados, sem percentuais especulativos.

**Dependências:** fases 6–8 e cobertura suficiente para o caminho que será testado.

**Critério de conclusão:** o caminho escolhido pode ser executado repetidamente em Windows e Linux com resultados observáveis, limitações documentadas e sem emulação/interpretação. A conclusão não se estende automaticamente ao jogo completo.

## Fase 10 — Avaliar e adaptar para Ultra Moon

**Tarefas**
- [ ] Confirmar identidade exata da versão-alvo e diferenças de código/módulos antes de reutilizar conclusões de Ultra Sun.
- [ ] Repetir análise, inventário e validação de unidades no alvo Ultra Moon.
- [ ] Verificar separadamente licenças, hashes locais e dependências; nenhum identificador local sensível deve ir para commits.
- [ ] Adaptar módulos e dados de configuração somente quando a evidência justificar.
- [ ] Repetir a matriz de testes do runtime e comparar diferenças conhecidas, usando referências técnicas independentes e fixtures permitidas — sem emulador ou interpretador.

**Dependências:** evidência suficiente de Ultra Sun e fases 2–9 para os componentes que se pretende compartilhar.

**Critério de conclusão:** o suporte a Ultra Moon tem sua própria prova reproduzível e matriz de compatibilidade. Não é declarado concluído apenas porque Ultra Sun executa ou porque uma ferramenta de análise compila.

