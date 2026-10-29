# Direção técnica do porte nativo

**Decisão registrada:** 26 de outubro de 2026.  
**Estado:** arquitetura escolhida para orientar a implementação; o runtime e o porte jogável ainda não existem.

## Objetivo de engenharia

Executar Pokémon Ultra Sun e Pokémon Ultra Moon como aplicações nativas de PC em Windows e Linux, começando por x86-64. A prioridade inicial é **conseguir executar corretamente uma parte real do jogo**, não obter alto FPS ou otimizar desempenho antecipadamente.

O produto não usará:
- emulação da CPU, GPU, sistema operacional ou periféricos do Nintendo 3DS;
- interpretador de instruções ARM/Thumb ou fallback interpretado para instruções não suportadas;
- JIT, virtualização de um console ou integração de um emulador como runtime;
- código de emulação ou interpretação como substituto temporário para cobrir lacunas do recompilador.

A recompilação é feita durante o desenvolvimento/construção: o decodificador reconhece instruções de origem, o tradutor gera C, e o compilador da plataforma transforma esse código em código de máquina nativo. Se uma instrução não estiver implementada e validada, a tradução deve falhar explicitamente; nunca deve encaminhá-la a um interpretador.

## Escolha de engine e bibliotecas

**Escolha: um runtime/engine nativo próprio em C++20, apoiado por SDL3 e Vulkan — não uma engine genérica pronta.**

| Componente | Decisão | Responsabilidade |
| --- | --- | --- |
| Runtime e integração | C++20 | Ciclo de vida da aplicação, módulos, ABI, memória e serviços de plataforma |
| Código recompilado | C gerado, compilado nativamente | Executar a lógica de máquina recompilada sem um interpretador ARM no produto |
| Janela, entrada e áudio | SDL3 3.4.18 como versão inicial a avaliar/pinar | Abstrações multiplataforma para janela, teclado, controle e dispositivos de áudio |
| Renderização de PC | Vulkan | Renderização direta pelo driver nativo; não criar uma GPU virtual PICA200 |
| Build | CMake + Ninja, com MSVC no Windows e GCC/Clang no Linux | Builds repetíveis por plataforma e integração de testes |
| Ferramentas de análise | Python 3.10+ | Inspeção estática, geração auxiliar, fixtures e automação; não é dependência de execução do jogo |

SDL3 é uma biblioteca de plataforma, não uma engine completa. Ela tem suporte oficial a Windows e Linux, acesso a janela/entrada/áudio e integração com APIs gráficas, incluindo Vulkan. O site oficial consultado em 26/10/2026 identifica SDL 3.4.18 como versão estável atual e publica a licença zlib. Fontes: [documentação SDL3](https://wiki.libsdl.org/SDL3/FrontPage), [versões SDL](https://github.com/libsdl-org/SDL/releases) e [licença/documentação SDL](https://github.com/libsdl-org/SDL/blob/main/docs/README.md). Referência gráfica oficial: [Vulkan Documentation](https://docs.vulkan.org/) e [tutorial de introdução do Khronos](https://docs.vulkan.org/tutorial/latest/00_Introduction.html), que documenta a API multiplataforma para Windows e Linux.

Não escolher Godot, Unity ou Unreal como base principal: o problema central não é criar um jogo novo com cenas, mas converter código ARM/Thumb existente para execução nativa e substituir serviços e caminhos gráficos do 3DS. Uma engine genérica não recompila esse código nem resolve o ABI, módulos, arquivos, sincronização e chamadas de serviço exigidos pelo alvo. Uma futura ferramenta auxiliar pode ser avaliada separadamente, mas não fará parte do caminho de execução sem uma decisão documentada.

## Revisão de referências em 29/10/2026

A comparação mais recente confirma que a escolha deve ser uma recompilação estática dedicada, não uma engine genérica nem a integração de um runtime de emulação:

- **[3dsrecomp](https://github.com/fearkov/3dsrecomp):** é a referência pública mais próxima do alvo: descobre funções ARM/Thumb/VFP e gera C. A implementação publicada, entretanto, depende do runtime Zakuro e direciona instruções não suportadas ao interpretador. Aproveitamos apenas ideias de descoberta de funções, geração de C e relatórios de cobertura; não é uma dependência ou base de runtime aceitável para esta direção.
- **[GBARecomp](https://github.com/mstan/gbarecomp):** é útil para estudar a separação entre análise, IR, codegen, runtime e testes, além de compilação nativa de código gerado. O código/fluxo publicado também inclui caminhos de interpretador e recuperação para PCs não resolvidos e foi criado para o hardware GBA; por isso, não será integrado como runtime nem usado para preencher lacunas do porte.
- **[Documentação Vulkan da Khronos](https://docs.vulkan.org/tutorial/latest/index.html):** confirma suporte multiplataforma a Windows/Linux e apresenta o material atual para Vulkan 1.4. Vulkan continua sendo a API gráfica prevista para a camada PC; isso não significa que a integração de renderização já exista.
- **[SDL3](https://wiki.libsdl.org/SDL3/FrontPage) e [releases oficiais](https://github.com/libsdl-org/SDL/releases):** SDL3 é a biblioteca de janela, entrada, controle e áudio escolhida para complementar o runtime C++20. A documentação atual identifica SDL 3.4.18 como versão estável em 29/10/2026; ela deve ser fixada no build somente quando a dependência for efetivamente integrada e testada.

**Regra de arquitetura:** essas fontes servem para pesquisa e comparação, não como autorização para copiar código. Nenhum caminho de runtime aceitará emulador de CPU/GPU, interpretador ARM/Thumb, JIT ou fallback interpretado. A execução de uma unidade real não suportada deve falhar de forma explícita. A validação nesta fase usa fixtures sintéticas e resultados esperados independentes; não executa o jogo num oráculo de interpretação.

## Arquitetura pretendida

1. **Intake local:** metadados, identidade do alvo, intervalos e arquivos de entrada autorizados são verificados localmente. Nenhuma ROM, extração, recurso proprietário, chave ou executável do jogo é enviada ao Git, Pages, CI ou releases.
2. **Análise estática:** descoberta e confirmação de funções, estado ARM/Thumb, fluxo de controle, referências, relocação, imports/exports e convenções de chamada. Não usar varredura linear cega como prova de que todo byte é código.
3. **Recompilação estática:** decodificador conservador → representação intermediária explícita → C gerado → compilador nativo. Registrar por unidade a origem, o endereço, o conjunto de instruções coberto e o resultado dos testes.
4. **Runtime nativo:** processo C++ com ABI definida para código gerado, memória, exceções/erros, módulos, threads, relógio, arquivos e salvamentos. Implementar somente serviços exigidos por caminhos já identificados.
5. **Renderização e áudio nativos:** reimplementar os caminhos necessários para APIs e recursos de PC. Vulkan deve executar comandos de renderização nativos; o projeto não deve construir um modelo de hardware PICA200 nem interpretar fluxos de comandos de uma GPU 3DS como dispositivo virtual.
6. **Entrada, persistência e ciclo de vida:** teclado/controle/touch, foco, temporização, salvamento atômico, backups e recuperação, tudo com contratos explícitos e testes independentes.
7. **Empacotamento:** distribuir somente código e dependências licenciadas e recursos cuja distribuição esteja autorizada. Dados particulares de entrada permanecem locais.

## Regras de qualidade

- Toda instrução reconhecida precisa de testes positivos, negativos e casos-limite apropriados; instruções desconhecidas devem ser rejeitadas.
- Validar comportamento com fixtures sintéticas, especificações independentes e tabelas de referência próprias. Não usar emulador ou interpretador como oráculo de execução.
- Distinguir código gerado, compilação da ferramenta, compilação de uma função e execução real de um caminho do jogo.
- Não declarar equivalência só porque o C compila ou o executável inicia. Comparar registradores, flags, memória e efeitos observáveis quando aplicável.
- Separar a lógica recompilada da implementação host; APIs, layouts de memória e convenções de chamada nunca devem ser presumidos sem evidência.
- Todos os relatórios partilhados devem excluir dados de jogo, chaves, caminhos pessoais, hashes privados e bytes extraídos.
- Não fazer otimização prematura. Primeiro demonstrar progresso funcional; medir e otimizar após haver um caminho real de execução.

## Próximo marco executável

**Marco N1 — pipeline de código nativo sem fallback.** Integrar a recompilação e a compilação C nativa a um pipeline reproduzível para Windows e Linux, com uma função sintética controlada e uma interface explícita de entrada/saída de registradores/flags. O pipeline precisa produzir um executável nativo, executá-lo e validar o resultado contra um oráculo sintético independente; encodings fora da cobertura devem terminar a tradução com erro. Não se deve afirmar que isso executa Pokémon.

**Marco N2 — primeira função real.** Em ambiente local do mantenedor, selecionar um intervalo autorizado de um alvo conhecido, confirmar estado ARM/Thumb e contrato da função, recompilar e validar os efeitos observáveis. Nenhum byte ou relatório derivado de entrada proprietária entra no repositório ou na CI. Não marcar o marco antes de registrar uma prova reproduzível e redigida.

**Marco N3 — primeiro caminho de jogo nativo.** Ligar unidades reais recompiladas ao runtime C++ e implementar somente os serviços estritamente necessários ao primeiro caminho executável. Cada caminho que dependa de instrução, API ou módulo não suportado bloqueia esse marco; não há fallback interpretado.

Só depois de N3 avançar para cobertura mais ampla de jogo, menus, progressão, renderização completa, áudio, salvamento e estabilidade. Ultra Moon terá validação própria; não se presumem equivalência ou compatibilidade a partir de Ultra Sun.

## Situação atual e limites

A `main` contém ferramentas de inspeção estática e demonstrações sintéticas limitadas de ARM A32/Thumb que geram C e têm testes de compilação/execução em código nativo. Elas **não** são um recompilador geral, não processaram um executável real de Ultra Sun/Ultra Moon nesta CI e não formam ainda um runtime Windows/Linux. O SDL3/Vulkan, a arquitetura C++20 e o pipeline N1 são decisões para o desenvolvimento futuro, não dependências já implementadas.

A incorporação de cada dependência exige fixar versão/commit, rever licença e dependências transitivas e atualizar [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Licenças de bibliotecas não autorizam o uso ou a distribuição de código ou recursos dos jogos.
