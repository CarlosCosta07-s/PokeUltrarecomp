# Auditoria dos projetos de referência

**Data da auditoria documental:** 24 de outubro de 2026.

## Escopo e método

Foram consultados os READMEs, documentação técnica disponível, metadados de licença/dependências presentes em arquivos de configuração, arquivos LICENSE encontrados e metadados de commits da branch padrão. Os links abaixo apontam para os repositórios e commits consultados.

Esta auditoria é documental. **Os builds, jogos e testes descritos pelos autores não foram executados de forma independente por PokeUltrarecomp.** Quando o status vem de um projeto externo, ele é descrito como reportado por esse projeto, não como validação nossa. Não houve cópia dos repositórios de referência para dentro deste projeto.

## Inspeção direta de código

Além dos documentos e manifests, foram inspecionados arquivos de implementação representativos. Isso não substitui uma auditoria arquivo por arquivo, nem significa que qualquer dependência tenha sido incorporada.

- **UltraSunnyMoon:** [clear_bss.c](https://github.com/tylergraydev/UltraSunnyMoon/blob/913eed4969163ea15e354dacb8e2bfe0a2439de5/src/runtime/clear_bss.c) implementa stores de 32 bits para zerar um intervalo de memória fixado para a versão-alvo; [aeabi_vec_ctor.c](https://github.com/tylergraydev/UltraSunnyMoon/blob/913eed4969163ea15e354dacb8e2bfe0a2439de5/src/runtime/aeabi_vec_ctor.c) reconstrói a rotina ABI que chama um construtor para cada elemento. A própria documentação classifica as rotinas como comportamentalmente testadas, mas não correspondentes byte a byte ao código original. Isso é código C reconstruído e integrado em uma imagem híbrida, não um runtime de PC.
- **3dsrecomp:** [src/main.rs](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/src/main.rs) expõe os comandos analyze/build/port/verify; [src/overrides.rs](https://github.com/fearkov/3dsrecomp/blob/c3f21f94ba50d688025febc8974ff348d471b587/src/overrides.rs) lê arquivos C e processa marcadores de overrides. Isso confirma uma ferramenta real de recompilação/override, não uma implementação de serviços Windows para cada jogo.
- **Zakuro:** [zakuro-core/src/lib.rs](https://github.com/fearkov/zakuro/blob/70b56de5a17eca8b3fa9316b31e24ac9eacd8f96/crates/zakuro-core/src/lib.rs) declara componentes para kernel HLE, memória, loader, serviços, estado e GPU; [services/dsp.rs](https://github.com/fearkov/zakuro/blob/70b56de5a17eca8b3fa9316b31e24ac9eacd8f96/crates/zakuro-core/src/services/dsp.rs) implementa comandos do serviço de áudio DSP, incluindo um caminho HLE. Isso comprova que a execução continua apoiada em uma camada de emulação de 3DS.
- **PokéMoon:** [pc/src/main.cpp](https://github.com/gradenGnostic/pokemoon/blob/7a5936eee5d08889d6cc534e6916a86b39fde694/pc/src/main.cpp) configura a raiz externa de dados e opções como limite de frames/headless; [pc/src/platform.cpp](https://github.com/gradenGnostic/pokemoon/blob/7a5936eee5d08889d6cc534e6916a86b39fde694/pc/src/platform.cpp) implementa entrada por SDL e integração OpenGL; [pc/src/title_resources.cpp](https://github.com/gradenGnostic/pokemoon/blob/7a5936eee5d08889d6cc534e6916a86b39fde694/pc/src/title_resources.cpp) interpreta buffers de recursos externos, e [pc/tests/game_manager_test.cpp](https://github.com/gradenGnostic/pokemoon/blob/7a5936eee5d08889d6cc534e6916a86b39fde694/pc/tests/game_manager_test.cpp) testa invariantes de ciclo de vida/alocação do gerenciador. É código host real e testável para componentes delimitados, mas não demonstra o jogo completo nem Ultra Moon.

## Resumo comparativo

| Projeto | Objetivo/resultado reportado | Modelo de execução | Licença observada | Utilidade e bloqueios |
| --- | --- | --- | --- | --- |
| [UltraSunnyMoon](https://github.com/tylergraydev/UltraSunnyMoon) | Reconstruir Pokémon Ultra Sun com funções legíveis e build verificável; documentação registra uma sequência limitada de gameplay no Azahar | Executável híbrido: código majoritariamente original e ambiente 3DS; não é runtime nativo de PC | Nenhum LICENSE encontrado no caminho consultado | Referência principal para evidência de reconstrução de Ultra Sun; reutilização de código bloqueada até permissão/licença confirmada |
| [3dsrecomp](https://github.com/fearkov/3dsrecomp) | Recompilador estático de ARM/Thumb/VFP para C; gera biblioteca carregada por Zakuro | Recompilação antecipada com intérprete como fallback no host | Cargo.toml declara MIT; arquivo LICENSE não foi encontrado no caminho consultado | Pode orientar ferramenta e verificação diferencial; a licença do commit exato precisa ser resolvida antes de incorporar código |
| [Zakuro](https://github.com/fearkov/zakuro) | Emulador HLE de Nintendo 3DS; sua matriz declara Ultra Sun e Ultra Moon jogáveis com código recompilado | Emulação de serviços/dispositivos de 3DS, recompilação AOT e interpretação residual | MIT; arquivo LICENSE localizado | Referência funcional mais direta para compatibilidade observada, mas não comprova uma porta nativa sem emulador |
| [PokéMoon](https://github.com/gradenGnostic/pokemoon) | Reconstrução da versão europeia base de Pokémon Moon; runtime de PC separado para lógica reconstruída parcial | Build de reconstrução 3DS e alvo host SDL2/OpenGL separados | Nenhum LICENSE encontrado no caminho consultado | Referência arquitetural para lógica portátil e host PC; não é Ultra Moon e não licencia automaticamente seu código |

## 1. UltraSunnyMoon

**Fontes e revisões consultadas**
- [README.md](https://github.com/tylergraydev/UltraSunnyMoon/blob/main/README.md)
- [STATUS.md](https://github.com/tylergraydev/UltraSunnyMoon/blob/main/docs/STATUS.md)
- [RUNTIME.md](https://github.com/tylergraydev/UltraSunnyMoon/blob/main/docs/RUNTIME.md)
- [PROJECT.md](https://github.com/tylergraydev/UltraSunnyMoon/blob/main/docs/PROJECT.md)
- [SETUP.md](https://github.com/tylergraydev/UltraSunnyMoon/blob/main/docs/SETUP.md)
- Commit observado no topo da branch principal durante a consulta: [913eed4969163ea15e354dacb8e2bfe0a2439de5](https://github.com/tylergraydev/UltraSunnyMoon/commit/913eed4969163ea15e354dacb8e2bfe0a2439de5). O status incluído nessa linha de trabalho data de 12 de outubro de 2026.

**Objetivo e alvo.** Projeto público de engenharia reversa/descompilação de Pokémon Ultra Sun, com reconstrução legível e build verificável do alvo fixado. Ultra Sun é o alvo primário; o projeto considera pesquisa de Pokémon Moon apenas quando a aplicabilidade é demonstrada.

**O que está implementado, segundo a documentação.** Ferramentas de análise/build e verificadores; reconstrução byte a byte do executável principal e de um CRO; algumas rotinas C não equivalentes byte a byte, mas testadas por comportamento e integradas em regiões delimitadas; verificações de preservação de bytes e empacotamento. O status mais recente consultado descreve original e build combinado chegando ao mesmo movimento controlável no quarto, após um filme de entrada fixo, com capturas e verificações de bytes em execução. Isso é um marco de caminho inicial limitado, não cobertura de jogo completo.

**Testes reportados.** A documentação relata testes de ferramentas, comparação pareada de frames e registros, leitura de bytes em runtime e revisão independente. O status indicado pela documentação era 60 testes de propriedade do projeto aprovados para o checkpoint descrito. Esses resultados são autorrelatados e não foram reexecutados por nós.

**Tipo de execução e dependências.** O projeto reconstrói funções específicas e empacota uma imagem que ainda retém a maior parte do código e dos recursos originais. A documentação diz explicitamente que o jogo reconstruído ainda necessita de um ambiente 3DS; o checkpoint utiliza Azahar. A substituição de gráficos, áudio, entrada, armazenamento, serviços de SO e carregamento de módulos por implementações host é trabalho posterior. A configuração documentada usa Windows com Ubuntu WSL para ferramentas, REA/Ghidra, Java, Python e CTRTool, entre outros. Isso descreve o ambiente de análise, não suporte a uma porta nativa de Windows.

**Licença.** A consulta ao caminho LICENSE não encontrou arquivo de licença. Não inferir permissão de cópia ou redistribuição a partir de o repositório ser público. Reutilização de código permanece bloqueada até que a licença e a procedência do conteúdo exato sejam confirmadas.

**Conclusão para PokeUltrarecomp.** É útil para estudar evidência de reconstrução, inventário de módulos, verificações de preservação e qualidade de testes. Não adotar o status de gameplay em Azahar como prova de runtime nativo, e não importar fontes sem resolver a licença.

## 2. 3dsrecomp

**Fontes e revisões consultadas**
- [README.md](https://github.com/fearkov/3dsrecomp/blob/main/README.md)
- [Cargo.toml](https://github.com/fearkov/3dsrecomp/blob/main/Cargo.toml)
- [ABI Cargo.toml](https://github.com/fearkov/3dsrecomp/blob/main/abi/Cargo.toml)
- Commit observado no topo da branch principal durante a consulta: [c3f21f94ba50d688025febc8974ff348d471b587](https://github.com/fearkov/3dsrecomp/commit/c3f21f94ba50d688025febc8974ff348d471b587).

**Objetivo e alvo.** Recompilador estático genérico para código de jogos Nintendo 3DS, projetado para funcionar com Zakuro, não uma porta dedicada a Ultra Sun/Ultra Moon.

**Implementação declarada.** Localiza funções no executável principal e em módulos CRO, gera C para ARM/Thumb/VFP, compila uma biblioteca host, oferece overrides C manuais e permite linkar um programa que continua lendo os arquivos do jogo. Há modo de verificar funções recompiladas contra o intérprete de Zakuro, comparando estado de CPU/memória.

**Testes reportados.** O README informa testes com Pokémon Alpha Sapphire, Pokémon Y, Majora’s Mask 3D e Persona Q e relata alta cobertura por instruções recompiladas para alguns títulos. Esse número de instruções não representa cobertura de gameplay nem prova de eliminação do runtime 3DS. O README da ferramenta, isoladamente, não enumera Ultra Sun/Ultra Moon como seus exemplos testados; a matriz do Zakuro lista os dois títulos como jogáveis com recompilação. Não executamos esses testes.

**Tipo de execução e dependências.** Código gerado vira biblioteca C compilada e carregada pelo emulador; código não encontrado ou não suportado continua no intérprete. O comando de “port” linka código em um executável próprio, mas o README afirma que esse executável ainda precisa dos arquivos do jogo e a integração pretendida é Zakuro. Portanto, “port” não basta para provar runtime de PC que substitui todos os serviços do 3DS.

**Plataformas e toolchain.** O README declara Linux e Windows, com Rust e compilador C; no Windows, GCC via MinGW-w64/MSYS2 ou WinLibs é mencionado. Cargo.toml declara Rust 1.88 como mínimo do pacote consultado. Isso é suporte da ferramenta, não uma declaração de que os jogos funcionem sem componentes de compatibilidade.

**Licença.** Cargo.toml declara MIT, mas não foi encontrado um arquivo LICENSE no caminho padrão consultado. A metadata é um indício público útil, mas o pacote precisa de confirmação jurídica/procedimental para o commit exato e para eventuais contribuições/subcomponentes antes de qualquer incorporação. Nenhum código foi copiado.

**Conclusão para PokeUltrarecomp.** É um candidato para estudar recompilação AOT e verificação diferencial. Um primeiro experimento deve usar um teste sintético sem arquivo de jogo e fixar o commit. A incorporação de código fica pendente até confirmar formalmente a licença aplicável.

## 3. Zakuro

**Fontes e revisões consultadas**
- [README.md](https://github.com/fearkov/zakuro/blob/main/README.md)
- [COMPATIBILITY.md](https://github.com/fearkov/zakuro/blob/main/COMPATIBILITY.md)
- [Cargo.toml](https://github.com/fearkov/zakuro/blob/main/Cargo.toml)
- [LICENSE](https://github.com/fearkov/zakuro/blob/main/LICENSE)
- Commit observado no topo da branch principal durante a consulta: [70b56de5a17eca8b3fa9316b31e24ac9eacd8f96](https://github.com/fearkov/zakuro/commit/70b56de5a17eca8b3fa9316b31e24ac9eacd8f96); a matriz consultada identificava a versão 0.2.29.

**Objetivo e alvo.** Emulador HLE experimental do Nintendo 3DS em Rust, usando recompilação antecipada de código de jogo em vez de JIT. Não é um projeto que transforma automaticamente cada jogo em aplicação Windows sem serviços de emulação.

**Implementação e testes reportados.** A matriz de compatibilidade lista Pokémon Ultra Sun (USA, title ID 00040000001B5000) e Pokémon Ultra Moon (USA, title ID 00040000001B5100) como “Playable”, com a coluna “Recompiled” marcada “Yes”. A definição de “Playable” no mesmo documento é ser jogável desde o início até o jogo. É uma afirmação de compatibilidade dos mantenedores, não um teste executado por PokeUltrarecomp nesta auditoria. Zakuro também mantém um intérprete para código que não foi coberto pela recompilação.

**Serviços de 3DS.** Por ser um emulador HLE, permanece responsável por modelar os dispositivos/serviços de 3DS que o jogo chama: execução e estado da CPU, memória, módulos, sistema de arquivos e salvamentos, serviços, temporização, entrada, áudio e gráficos. A lista precisa de chamadas específicas só pode ser fechada após inspeção do alvo/caminhos selecionados.

**Plataformas e compiladores.** O README declara builds Windows e Linux. O Cargo.toml consultado declara Rust 1.95 ou mais recente; Linux requer, entre outras coisas, pkg-config e bibliotecas de desenvolvimento ALSA/udev. A recompilação do código do jogo requer compilador C, com GCC/Clang ou oferta de Zig mencionados no README. O projeto tem licença MIT e arquivo LICENSE localizado; o texto exige preservação do aviso de copyright/licença e contém renúncia de garantia.

**Limitações para uma porta nativa.** A compatibilidade dentro de Zakuro não significa execução sem o modelo HLE do 3DS. O código recompilado pode continuar dependendo do intérprete, de loader de módulos e de dados externos. Adotar Zakuro inteiro também seria uma dependência grande e exigiria decisão arquitetural e auditoria de componentes; esta tarefa não copia o emulador.

**Conclusão para PokeUltrarecomp.** É a referência mais direta para entender que Ultra Sun e Ultra Moon têm caminho de execução experimental em PC, mas o estado deve ser classificado como emulação com recompilação AOT/fallback, não como prova de porta nativa independente.

## 4. PokéMoon

**Fontes e revisões consultadas**
- [README.md](https://github.com/gradenGnostic/pokemoon/blob/main/README.md)
- [BUILD.md](https://github.com/gradenGnostic/pokemoon/blob/main/docs/BUILD.md)
- [CMakeLists.txt](https://github.com/gradenGnostic/pokemoon/blob/main/CMakeLists.txt)
- Commit observado no topo da branch principal durante a consulta: [7a5936eee5d08889d6cc534e6916a86b39fde694](https://github.com/gradenGnostic/pokemoon/commit/7a5936eee5d08889d6cc534e6916a86b39fde694).

**Objetivo e alvo.** Reconstruir Pokémon Moon, região europeia, release base 1.0; não é Pokémon Ultra Moon. A documentação fixa a identidade do alvo e mantém inputs retail fora do repositório.

**O que está implementado, segundo a documentação.** Manifesto de funções reconstruídas, scripts de análise/build e uma pipeline para reconstrução do binário de 3DS. O README registra 2.984 funções source-backed entre 18.945 inventariadas (15,75%); 298 correspondências ARM exatas e 53 funções marcadas como prontas para runtime no estado descrito. O build diferencia correspondência binária exata, equivalência semântica e prontidão para runtime; esses rótulos não são intercambiáveis.

**Runtime de PC.** O README e CMakeLists definem um alvo host separado, com lógica C++ portátil parcial e camadas de aplicação/plataforma usando SDL2 e OpenGL. Ele tem testes de inicialização headless e testes unitários de componentes. A documentação deixa claro que o alvo host não integra o build de 3DS nem substitui o renderer 3DS. Recursos retail ficam externos, sob um diretório de dados local. É evidência de uma arquitetura de runtime parcial, não de que o jogo inteiro seja jogável como aplicação PC. Os comandos de build documentados são para Linux (CMake, C++17, SDL2, OpenGL e Ninja); suporte formal a Windows não foi estabelecido pelos documentos consultados.

**Testes reportados.** BUILD.md descreve verificações da pipeline, comparação de bytes ARM, seleção de objetos e testes de componentes host. Não executamos esses comandos. O build canônico exige entradas locais extraídas do jogo e uma versão fixada da 3DS Decomp Pipeline; essas entradas e saídas não podem ir para Git ou CI.

**Licença.** Não foi encontrado arquivo LICENSE no caminho padrão consultado, e o README consultado não declara uma licença geral. A reutilização de código está bloqueada até confirmação de permissão e dos cabeçalhos de cada arquivo. Não inferir licença pelo caráter público do repositório.

**Conclusão para PokeUltrarecomp.** Útil para aprender com uma separação explícita entre lógica reconstruída e adapters host, manifestos e testes. A aplicabilidade a Ultra Moon deve ser demonstrada função por função, e não presumida apenas pela semelhança do nome ou da série.

## Decisões resultantes

1. Nenhum repositório de referência será copiado para PokeUltrarecomp.
2. A primeira prova de conceito deve usar testes sintéticos sem ROM, firmware, chave ou recursos extraídos.
3. Zakuro e 3dsrecomp são referências técnicas para estudar recompilação AOT e compatibilidade, mas não satisfazem por si sós o requisito de runtime próprio.
4. PokéMoon fornece uma referência de arquitetura host, mas sua licença e aplicabilidade precisam ser resolvidas antes da reutilização; ele também não é o mesmo jogo-alvo.
5. O estado de licença incerto em UltraSunnyMoon, 3dsrecomp e PokéMoon é um bloqueio à cópia de código até confirmação. A licença MIT encontrada em Zakuro não se estende a outros repositórios nem aos jogos/dados da Nintendo.
6. Esta auditoria não constitui análise jurídica nem garante a licitude de descompilação, extração, recompilação ou contorno de proteção tecnológica.
