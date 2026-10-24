# Roadmap técnico

Este roadmap é um plano de trabalho, não uma declaração de funcionalidades implementadas. Nenhuma fase deve ser marcada como concluída sem evidências revisáveis. O critério de aceitação é a condição mínima para encerrar cada fase; descobertas podem exigir tarefas adicionais.

## Fase 1 — Organização e auditoria

**Estado:** documentação e auditoria inicial publicadas; pendente decisão do mantenedor sobre o LICENSE preexistente e revisão final de governança.

**Tarefas**
- [ ] Manter README, arquitetura, regras de contribuição, segurança e avisos legais consistentes.
- [ ] Registrar os commits e documentos de cada projeto de referência em [AUDIT.md](AUDIT.md).
- [ ] Separar fatos publicados, evidências autorrelatadas, hipóteses e perguntas abertas.
- [ ] Confirmar que não há conteúdo de jogo, segredos, chaves ou artefatos de build no Git.
- [ ] Revisar o arquivo LICENSE preexistente, cuja procedência e abrangência não estão documentadas.

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

**Tarefas**
- [ ] Selecionar uma prova de teste sintética ou um teste de unidade publicado por uma ferramenta de referência que não exija ROM/dump.
- [ ] Preferir um teste de compilação, verificação de instruções reconstruídas contra um intérprete ou teste do runtime de PC com fixtures sintéticas.
- [ ] Fixar o commit exato da ferramenta e as versões de compilador/dependências.
- [ ] Registrar comandos, saída completa relevante, código de saída e resultado em BUILD_NOTES.md.
- [ ] Se o teste escolhido exigir arquivo de jogo local, avaliar primeiro um caso sintético alternativo. Não enviar a entrada, sua extração nem saída derivada ao Git/CI.

**Dependências:** fases 2 e 3.

**Critério de conclusão:** outra pessoa pode reproduzir o mesmo teste com ferramentas permitidas e sem arquivos proprietários; o resultado deste repositório é explicitamente identificado como sucesso, falha ou inconclusivo.

## Fase 5 — Definir a primeira prova de conceito

**Tarefas**
- [ ] Escolher apenas uma unidade pequena, com limite de escopo e um resultado observável.
- [ ] Definir entrada sintética permitida, saída esperada, dependências e como demonstrar a origem do código.
- [ ] Decidir se a prova testa recompilação de uma função, camada de abstração ou comportamento de um runtime host.
- [ ] Separar compilação da ferramenta, compilação de código reconstruído e execução no host.
- [ ] Criar testes automatizáveis que não necessitem de dumps ou recursos extraídos.

**Dependências:** fase 4 aprovada e licenças da ferramenta confirmadas.

**Critério de conclusão:** existe uma especificação curta aprovada com comando reproduzível, teste de sucesso, teste negativo e evidência que distingue a prova de conceito de um jogo funcional.

## Fase 6 — Investigar runtime próprio para Windows

**Tarefas**
- [ ] Inventariar chamadas de sistema, serviços do 3DS e contratos de runtime exigidos pelos caminhos de código selecionados.
- [ ] Mapear estado da CPU, exceções, memória, sincronização, módulos dinâmicos e callbacks.
- [ ] Estudar se código recompilado pode operar sem o emulador e quais stubs ainda seriam necessários.
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
