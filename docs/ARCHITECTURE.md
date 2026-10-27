# Arquitetura do porte nativo

**Estado em 26/10/2026:** a direção técnica foi escolhida, mas esta arquitetura ainda não está implementada. Consulte [Direção técnica do porte nativo](NATIVE_PORT_DIRECTION.md) para as decisões e os marcos N1–N3.

## Requisitos não negociáveis

- Executar código recompilado como código de máquina nativo de PC em Windows e Linux, começando por x86-64.
- Não incluir emulador de Nintendo 3DS, intérprete ARM/Thumb, JIT ou fallback de interpretação.
- Não emular CPU/GPU/periféricos do 3DS. Serviços necessários serão implementados nativamente e os caminhos gráficos serão reimplementados sobre APIs de PC.
- Rejeitar durante a tradução qualquer instrução, relocação, ABI ou serviço ainda não implementado e validado.
- Manter ROMs, extrações, recursos, chaves, executáveis e relatórios privados fora do GitHub e de qualquer CI.
- Provar comportamento antes de otimizar; distinguir cada estágio por resultados reproduzíveis.

## Visão em camadas

1. Entradas locais autorizadas e perfil de alvo.
2. Intake e validação de metadados do alvo.
3. Análise estática ARM/Thumb, limites de função e módulos.
4. Decodificador conservador → representação intermediária (IR) → gerador de C.
5. Compilador nativo do host, produzindo unidades de código de máquina de PC.
6. Runtime próprio em C++20, com ABI, memória, serviços, arquivos, módulos e sincronização.
7. SDL3 para janela, entrada e áudio; Vulkan para renderização nativa de PC.

Python é usado somente por ferramentas de desenvolvimento e validação. O C gerado deve ser compilado pelo toolchain nativo; o executável final não pode precisar de um interpretador ARM nem executar um laço que decodifique instruções do convidado.

## 1. Recompilação estática

O pipeline precisa separar quatro responsabilidades:

1. **Descoberta/análise:** limites de função, fluxo de controle, estado ARM/Thumb, literais, tabelas, referências, chamadas, relocação, módulos dinâmicos e informações necessárias ao ABI.
2. **Decodificação:** cada encoding é classificado como suportado, explicitamente inválido ou desconhecido. Não inventar semântica.
3. **Representação intermediária (IR):** representar operações, predicação, flags, memória, transferências de controle e chamadas de maneira que possa ser testada isoladamente.
4. **Emissão/compilação:** gerar código C determinístico, compilar com MSVC/GCC/Clang para código nativo e ligar a uma interface C estável do runtime.

Cada unidade traduzida precisa registrar endereço de origem, estado ARM/Thumb, conjunto de instruções, dependências, interface de entrada/saída, evidência de teste e limitações. Não tratar uma função como válida apenas porque compilou. Não aceitar varredura linear indiscriminada em uma seção .text como descoberta de funções.

## 2. ABI, memória e estado da CPU

A interface entre C gerado e runtime deve especificar largura/alinhamento, endianness, registradores vivos, flags, stack pointer, convenções de chamada, comportamento de retorno, exceções, callbacks e dependências de estado global. Endereços de origem não podem ser tratados como ponteiros de host sem uma decisão explícita de mapeamento.

Memória do alvo, buffers e regiões mapeadas precisam ter propriedade, tamanho, permissões e vida útil definidos. Não representar falhas de memória como leituras inventadas. Transferências de controle indiretas só podem ser geradas quando o destino puder ser resolvido ou representado por uma interface nativa explícita.

## 3. Runtime e serviços de plataforma

O runtime próprio em C++20 será responsável por ciclo de vida, módulos, memória e serviços de PC, com interfaces testáveis para:

- relógio monotônico, temporizadores e espera;
- threads, mutexes, eventos, sincronização e encerramento;
- diretórios de usuário, leitura e gravação, escrita atômica, backup e recuperação;
- carregamento de módulos, relocação e resolução de imports/exports;
- entrada, foco da janela e conexão/desconexão de dispositivos;
- áudio, pausa, latência e perda/recuperação do dispositivo;
- chamadas de sistema/serviços do 3DS efetivamente necessários ao caminho recompilado.

Não criar stubs ou interfaces sem comportamento para preencher diretórios. Antes de implementar cada serviço, identificar uma chamada real ou uma dependência comprovada do caminho em execução. Se o serviço ainda não estiver pronto, esse caminho não pode ser marcado como executável.

## 4. Engine, janela, áudio e gráficos

A camada de runtime/engine será desenvolvida em C++20; SDL3 fornece a interface multiplataforma para janela, teclado, controles e áudio. Vulkan será a API gráfica de PC, acessada diretamente, em vez do SDL_Renderer.

A seleção permite controle sobre gráficos 3D e builds Windows/Linux. A versão inicial a avaliar e fixar é SDL 3.4.18, versão identificada como estável no site oficial consultado em 26/10/2026; a licença publicada é zlib. Fontes: [documentação SDL3](https://wiki.libsdl.org/SDL3/FrontPage), [versões oficiais](https://github.com/libsdl-org/SDL/releases) e [README/licença SDL](https://github.com/libsdl-org/SDL/blob/main/docs/README.md).

**Vulkan não torna automaticamente o código gráfico do 3DS compatível.** O projeto precisará entender quais operações gráficas o jogo realmente usa e reimplementar seus resultados com recursos e shaders nativos de PC. Não criar uma GPU virtual PICA200 nem um interpretador de listas de comandos de GPU. O caminho de renderização precisa ter fixtures sintéticas, critérios observáveis e testes de ciclo de vida/sincronização.

Godot, Unity e Unreal não serão a engine central: não resolvem a recompilação do executável ARM original nem os serviços esperados por ele, e imporiam uma camada de integração desnecessária antes de existir código recompilado executável. SDL3 e Vulkan são bibliotecas/APIs dentro do runtime próprio, não uma alegação de que a engine já existe.

## 5. Arquivos, salvamentos e conteúdo local

Separar recursos locais autorizados, arquivos temporários, configuração e progresso salvo. A persistência deve oferecer formato/versionamento documentado, integridade, escrita atômica, backup e recuperação após falha. Nunca pesquisar recursos em diretórios arbitrários nem sobrescrever arquivos que não pertencem ao runtime.

Nenhum dado do jogo entra em commits, GitHub Pages, releases, issues, logs públicos ou CI. Relatórios compartilhados devem ser redigidos e não devem revelar caminhos do usuário, hashes privados, bytes extraídos, chaves ou conteúdo proprietário.

## 6. Testes e critérios de conclusão

A validação será organizada em camadas:

- testes unitários para decodificador e IR, incluindo entradas inválidas e encodings desconhecidos;
- execução nativa de C gerado em fixtures sintéticas;
- testes de flags, registradores, fluxo de controle, memória e ABI com oráculos independentes baseados na especificação;
- compilação e testes multiplataforma Windows/Linux;
- teste local de funções reais selecionadas, sem publicar entradas ou saídas proprietárias;
- testes host de entrada, áudio, arquivos, sincronização e renderização com dados sintéticos;
- testes de integração de caminhos do jogo, progressão e salvamento, executados localmente pelo mantenedor.

Nenhum emulador ou interpretador será usado como runtime ou oráculo de execução. Um teste só pode afirmar exatamente o que exercitou. A compilação de uma ferramenta, o sucesso de um subconjunto sintético e a execução de uma função não provam que o jogo inicia ou é jogável.

## Decisões registradas e itens pendentes

**Decidido**
- Runtime próprio em C++20; código recompilado C compilado nativamente.
- SDL3 para janela, input e áudio; Vulkan para renderização nativa de PC.
- CMake + Ninja; compiladores MSVC no Windows e GCC/Clang no Linux.
- Ferramentas Python fora do caminho de execução.
- Proibição de emulação, interpretação, JIT e fallback para instruções desconhecidas.

**Ainda precisa de implementação ou evidência**
- Descoberta de funções e cobertura semântica suficiente de ARM, Thumb, Thumb-2 e VFP.
- Identificação de ABI, referências, tabelas, relocação, imports/exports e módulos dinâmicos reais.
- Primeira função real recompilada e validada localmente.
- Serviços do 3DS realmente exigidos pelos caminhos selecionados.
- Caminho nativo de gráficos e áudio que não modele hardware 3DS.
- Build/testes reproduzíveis em Windows e Linux e matriz de validação de jogo.

A adoção de SDL3/Vulkan deve ser formalizada nos arquivos de dependências e em [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) antes de incorporá-los ao build. A licença de uma biblioteca não concede direitos sobre o jogo ou seus recursos.
