# Roadmap técnico

Este roadmap é um plano de trabalho, não uma declaração de funcionalidades implementadas. Nenhuma fase deve ser marcada como concluída sem evidências revisáveis. O critério de aceitação é a condição mínima para encerrar cada fase; descobertas podem exigir tarefas adicionais.

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

**Estado:** ferramenta local de preflight implementada e coberta por fixtures sintéticas. Lê o Program ID no ACI do ExHeader, confere o alvo e calcula os offsets no `.code` com o layout page-padded declarado. Os arquivos reais dos jogos não são incluídos nem processados na CI.

**Tarefas desta etapa**
- [x] Adicionar perfis distintos de Ultra Sun e Ultra Moon, com IDs-base/atualização conhecidos e política de entradas locais.
- [x] Ler SCI e Program ID do ACI, validar o alvo embutido, endereços, páginas, tamanhos, sobreposição e comprimento exato do `.code` page-padded; reportar offsets dos segmentos.
- [x] Emitir JSON com SHA-256 local e metadados sem copiar bytes ou caminhos absolutos.
- [x] Expor candidatos de variante por tamanho de `.code` a partir de referência comunitária; o resultado é explicitamente heurístico e não autentica a revisão.
- [x] Adicionar testes sintéticos de sucesso, falha, incompatibilidade de título e CLI.
- [ ] Validar uma entrada local autorizada e ainda não modificada de cada jogo; registrar apenas relatório redigido.
- [ ] Fazer inventário de funções ARM/Thumb sem reutilizar fontes cuja licença não está confirmada.

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

## Fase 6 — Investigar runtime próprio para Windows

**Direção do projeto:** o objetivo é execução nativa no Windows, sem dependência de emulador no runtime. Se surgir uma necessidade concreta de comparar o comportamento do jogo original, o Azahar poderá ser usado apenas como referência externa opcional, sem ser incorporado ao produto.

**Tarefas**
- [ ] Inventariar chamadas de sistema, serviços do 3DS e contratos de runtime exigidos pelos caminhos de código selecionados.
- [ ] Mapear estado da CPU, exceções, memória, sincronização, módulos dinâmicos e callbacks.
- [ ] Definir e implementar a camada host necessária para executar código recompilado sem depender de um emulador de Nintendo 3DS.
- [ ] Comparar alternativas de renderização e janela no Windows com uma prova isolada; não escolher API com base em suposição.
- [ ] Documentar limites e dependências remanescentes para cada caminho exercitado.

**Dependências:** fase 5.

**Critério de conclusão:** um documento de viabilidade identifica a primeira parte executável de forma independente, as interfaces em falta, as dependências de terceiros e critérios para provar que não é um executável híbrido.

## Fase 7 — Substituição gradual dos serviços do Nintendo 3DS

**Tarefas**
- [ ] Implementar apenas uma interface host necessária a uma unidade já reconstruída e licenciada.
- [ ] Começar por serviços isolados e testáveis, como temporizadores, entrada ou acesso abstrato a arquivos.
- [ ] Registrar o comportamento de referência e testes diferenciais.
- [ ] Não presumir que serviços equivalentes têm as mesmas semânticas, ordenação ou sincronização.
- [ ] Manter todas as entradas de usuário locais fora do Git e da CI.

**Dependências:** fase 6 e evidência técnica suficiente do serviço selecionado.

**Critério de conclusão:** a interface selecionada funciona no host Windows com testes positivos, negativos e de regressão; chamadas não substituídas são listadas explicitamente.

## Fase 8 — Validar gráficos, áudio, entrada e salvamento

**Tarefas**
- [ ] Definir testes de renderização sem recursos proprietários e documentar equivalência visual mensurável.
- [ ] Testar áudio sintético, latência e ciclo de vida do dispositivo.
- [ ] Testar teclado, controle, foco da janela e remapeamento.
- [ ] Testar salvamento em diretório externo com gravação atômica, corrupção simulada e recuperação.
- [ ] Verificar resolução, proporção, temporização de quadros e sincronização entre subsistemas.
- [ ] Separar testes de infraestrutura de qualquer execução de jogo real.

**Dependências:** fases 6 e 7; cada subsistema deve ter uma interface host funcional.

**Critério de conclusão:** relatórios de testes reproduzíveis cobrem cada subsistema e suas falhas, sem declarar cobertura de gameplay que não foi exercitada.

## Fase 9 — Estabilidade e desempenho

**Tarefas**
- [ ] Definir uma matriz de hardware/Windows/driver e uma carga de teste permitida.
- [ ] Medir inicialização, uso de memória, CPU/GPU, tempos de quadro e falhas com ferramenta identificada.
- [ ] Testar ciclos repetidos de inicialização/encerramento, perda de foco, dispositivo de áudio e controle desconectado.
- [ ] Corrigir vazamentos, deadlocks, corrupção de estado e falhas de recuperação antes de ampliar escopo.
- [ ] Publicar medições com condições de execução e limitações.

**Dependências:** fase 8.

**Critério de conclusão:** o conjunto definido passa repetidamente em ambiente documentado e os problemas conhecidos estão registrados; resultados não são generalizados para hardware não testado.

## Fase 10 — Avaliar e adaptar para Ultra Moon

**Tarefas**
- [ ] Confirmar identidade exata da versão-alvo e diferenças de código/módulos antes de reutilizar conclusões de Ultra Sun.
- [ ] Repetir análise, inventário e validação de unidades no alvo Ultra Moon.
- [ ] Verificar separadamente licenças, hashes locais e dependências; nenhum identificador local sensível deve ir para commits.
- [ ] Adaptar módulos e dados de configuração somente quando a evidência justificar.
- [ ] Repetir a matriz de testes do runtime e comparar diferenças conhecidas.

**Dependências:** evidência suficiente de Ultra Sun e fases 2–9 para os componentes que se pretende compartilhar.

**Critério de conclusão:** o suporte a Ultra Moon tem sua própria prova reproduzível e matriz de compatibilidade. Não é declarado concluído apenas porque Ultra Sun funciona, nem porque um emulador lista o jogo como jogável.
