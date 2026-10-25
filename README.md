# PokeUltrarecomp

**Estado: fase inicial de pesquisa, documentação, auditoria e ferramentas de verificação do repositório.** Este repositório ainda não contém uma porta funcional de Pokémon Ultra Sun ou Pokémon Ultra Moon, um runtime próprio para Windows, nem resultados de compilação da porta ou testes de jogo executados por este projeto.

## Objetivo

Investigar uma possível porta para Windows de **Pokémon Ultra Sun** e **Pokémon Ultra Moon**, preservando tanto quanto legalmente permitido a lógica e o comportamento dos jogos e estudando como substituir os serviços específicos do Nintendo 3DS por implementações para PC.

A estratégia inicial é estudar projetos de reconstrução, descompilação, recompilação e emulação existentes, aproveitar apenas resultados tecnicamente demonstrados e evitar reescritas desnecessárias. A existência de um emulador, de código C/C++ gerado ou de uma cena inicial funcional não prova, por si só, que um jogo foi portado nativamente.

## Estado atual verificável

- O trabalho deste repositório está limitado à organização, documentação, pesquisa inicial e ferramentas locais de proteção/verificação; o runtime do jogo ainda não foi implementado.
- Este conjunto de documentos registra uma auditoria documental dos quatro projetos de referência listados abaixo. Os testes reportados por esses projetos foram lidos em suas documentações, mas **não foram executados independentemente por este repositório**.
- Ainda não há runtime próprio implementado aqui, teste de jogo reproduzível ou porta nativa funcional reivindicada. A POC-001 é um experimento sintético limitado e não constitui runtime nem porta.
- O arquivo **LICENSE** já existia no repositório inicial e contém o texto padrão da GNU GPL versão 3. Sua procedência, autoria e abrangência não estão documentadas. Por isso, não se deve interpretar esse arquivo como confirmação de que todo conteúdo presente ou futuro pode ser licenciado pelo mantenedor. Veja [Legal e propriedade intelectual](docs/LEGAL_AND_IP.md).
- Nenhuma ROM, dump, firmware, chave, executável ou recurso proprietário deve entrar no Git, em issues, releases ou CI.

## Jogos-alvo

| Jogo | Objetivo | Estado neste projeto |
| --- | --- | --- |
| Pokémon Ultra Sun | Investigar uma porta nativa para Windows | Pesquisa; nenhuma porta implementada |
| Pokémon Ultra Moon | Adaptar resultados comprovados e validar diferenças | Pesquisa futura; nenhuma porta implementada |

## Projetos de referência

A avaliação e os limites de reutilização estão em [docs/AUDIT.md](docs/AUDIT.md).

- [UltraSunnyMoon](https://github.com/tylergraydev/UltraSunnyMoon) — pesquisa e reconstrução de Pokémon Ultra Sun; seu estado documentado ainda exige um ambiente de 3DS para executar o jogo reconstruído.
- [3dsrecomp](https://github.com/fearkov/3dsrecomp) — recompilador estático de código ARM/Thumb para C, projetado para funcionar com Zakuro.
- [Zakuro](https://github.com/fearkov/zakuro) — emulador HLE do Nintendo 3DS que usa recompilação antecipada e interpretação como fallback.
- [PokéMoon](https://github.com/gradenGnostic/pokemoon) — reconstrução de Pokémon Moon e um alvo separado de runtime para PC; não é uma porta pronta de Ultra Moon.

Esses links são fontes de estudo, não dependências aprovadas para incorporação. Não copiamos repositórios completos. Antes de reutilizar código, é obrigatório verificar licença, commit de origem, autores, dependências, avisos e procedência.

## Aviso de independência

PokeUltrarecomp é um projeto independente de pesquisa e fãs. Não é afiliado, patrocinado, autorizado ou endossado pela Nintendo, GAME FREAK, Creatures Inc. ou The Pokémon Company. Pokémon, os títulos dos jogos, personagens e demais propriedades relacionadas pertencem aos respectivos titulares.

Esse aviso não é autorização, não concede direitos e não oferece imunidade contra reclamações. Consulte [docs/LEGAL_AND_IP.md](docs/LEGAL_AND_IP.md).

## Roadmap

O plano executável está em [docs/ROADMAP.md](docs/ROADMAP.md). A arquitetura proposta — ainda não implementada — está em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Registro de ferramentas e testes reproduzíveis: [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md).

As fases são:

1. Organizar o projeto e registrar a auditoria.
2. Confirmar licenças, procedência e dependências.
3. Preparar e documentar o ambiente Windows/WSL.
4. Reproduzir um teste documentado de referência sem distribuir conteúdo proprietário.
5. Escolher uma prova de conceito pequena e mensurável.
6. Investigar os requisitos de um runtime próprio para Windows.
7. Substituir gradualmente os serviços de 3DS necessários.
8. Validar gráficos, áudio, entrada e salvamento.
9. Avaliar estabilidade e desempenho com evidências.
10. Avaliar e validar a adaptação para Ultra Moon.

## Primeira verificação reproduzível

A primeira tarefa de teste está documentada em [docs/REFERENCE_TEST_001.md](docs/REFERENCE_TEST_001.md) e usa um script PowerShell local. O script executa testes sintéticos do parser de overrides do 3dsrecomp numa revisão fixada, sem arquivos de jogo e sem depender do GitHub Actions. O teste ainda não foi executado neste ambiente porque Rust/Cargo não estão instalados. Mesmo aprovado, demonstra apenas o comportamento do parser, não recompilação ou execução de qualquer jogo.

## Verificação local do repositório

Foi adicionado um verificador sem dependências externas para ajudar a detectar caminhos/arquivos com aparência de conteúdo de jogo ou dados privados e links Markdown relativos quebrados:

    python tools/check_repository_safety.py
    python -m unittest discover -s tests -v

É necessário Python 3.10 ou mais recente e Git. O verificador analisa os blobs preparados no índice Git, as versões atuais dos arquivos na pasta de trabalho e arquivos não ignorados ainda não rastreados. Isso permite detectar diferenças entre o que será commitado e o que está no disco. Ele não examina o histórico inteiro, arquivos ignorados não rastreados, o conteúdo semântico de arquivos binários ou a situação jurídica das fontes. Não substitui revisão do diff, nem comprova que a porta funciona. O uso de `.gitignore` continua sendo uma barreira adicional, não uma garantia.

## Pesquisa de bases de código

Foi criada uma pesquisa de **nove repositórios de código** relacionados a recompilação ARM, emulação, decodificação e validação: [docs/CODEBASE_RESEARCH.md](docs/CODEBASE_RESEARCH.md). Inclui observações técnicas e notas de licença para distinguir referências de código realmente autorizadas para reutilização. Nenhum código de terceiro foi copiado.

## Prova de conceito sintética ARM A32 → C

Foi adicionada a [POC-001](docs/POC_001_SPEC.md), uma demonstração original e restrita que traduz fixtures ARM A32 sintéticas para C. As instruções de dados suportadas aceitam predicação pelas 14 condições padrão de ARM (EQ a LE), assim como os desvios `B`. `ADDS`, `SUBS`, `CMN` e `CMP` imediatos atualizam NZCV; instruções predicadas que não passam na condição preservam registradores e flags. O estado de entrada NZCV é selecionado na geração por `translate(..., initial_nzcv=...)` ou `--initial-nzcv`. A matriz nativa cobre 448 combinações de desvio/predicação (14 condições × 16 estados NZCV) com uma tabela de condições independente, além dos 96 casos aritméticos da matriz diferencial. O tradutor agora aceita desvios para trás/autoalvo **somente** quando é fornecido um orçamento explícito entre 1 e 100.000 instruções executadas (`max_execution_steps` ou `--max-execution-steps`); o C gerado relata término normal (status 0) ou esgotamento do orçamento (status 1) e a contagem de passos. Sem orçamento, a API original permanece igual e laços continuam rejeitados.

A suíte completa do repositório passou em **151 testes, sem falhas ou testes ignorados**, no checkout completo do commit `78bad708b8e561d58f934f133fef68d9e1d1f2cb`, em Ubuntu com Python 3.14.4 e GCC 15.2.0. Isso inclui 136 testes prévios e 15 casos novos para a ferramenta de inspeção de intervalo explícito ARM/Thumb. A matriz diferencial registou 96/96 correspondências; a matriz Thumb valida 224 combinações (14 condições × 16 estados NZCV); o verificador de segurança passou após analisar 38 caminhos indexados. [Registro da execução integral](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40158948344). Isso valida a análise sintática limitada e o intake de metadados, não a execução do jogo nem compatibilidade com Pokémon Ultra Sun/Ultra Moon.

    python tools/arm_subset_poc.py
    python tools/arm_differential_poc.py
    python -m unittest discover -s tests -v

A POC traduz a fixture padrão de dez palavras, que usa `MOV`, `SUB`, `ADD`, `AND`, `ORR`, `EOR`, `BIC`, `MVN` e `BX LR`. O subconjunto ainda não inclui `BL`, saltos para trás sem orçamento, memória, funções reais, o CPSR completo, Thumb, formas lógicas com bit S ou shifter-carry. Nada disso lê ROMs nem dados de jogo, constitui um recompilador geral, demonstra suporte a Windows ou representa uma porta de Pokémon. Veja [escopo, comandos e limites](docs/POC_001_SPEC.md).

## Preparação dos executáveis de Ultra Sun / Ultra Moon

A POC-002 agora traduz também ADD/SUB Thumb-1 de três operandos (registrador e imediato de 3 bits), incluindo atualização de NZCV validada com C nativo. Também traduz LSL/LSR/ASR Thumb-1 com imediato e valida os casos especiais de deslocamento zero em C nativo. A suíte completa mais recente passou em 224 testes no [workflow](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40195030086).

O inspetor de intervalos também produz um grafo candidato de fluxo de controle: blocos básicos, arestas de branches condicionais, transferências externas e avisos para instruções desconhecidas e sobreposição com literais. Isso ainda é uma anotação estática limitada ao intervalo escolhido, não descoberta automática de funções nem prova de execução do jogo.


Foi iniciado um caminho específico para os dois alvos: os perfis `targets/pokemon_ultra_sun.json` e `targets/pokemon_ultra_moon.json` e a ferramenta `tools/inspect_3ds_target.py` conferem metadados do ExHeader e de `.code` descomprimido fornecido localmente. O relatório lê o Program ID de 64 bits embutido no ACI, confere-o contra os perfis dos dois jogos, inclui offsets no `.code` para `.text`, `.rodata` e `.data`, stack/BSS e hashes SHA-256 locais. Exige que o `.code` descomprimido corresponda exatamente ao layout page-padded declarado pelo ExHeader; IDs desconhecidos e revisões não confirmadas são tratados conservadoramente. Também apresenta candidatos de revisão para dois tamanhos de `.code` registrados numa referência comunitária, sempre como correspondência por tamanho — não como prova de versão ou autenticidade. Os testes usam ExHeaders e bytes totalmente sintéticos; a CI não lê nem exige ROM, dump ou arquivo extraído dos jogos.

Exemplo (substitua por caminhos locais de entradas do mesmo executável):

    python tools/inspect_3ds_target.py --target ultra-sun --exheader /local/exheader.bin --code /local/code.bin --title-id 00040000001B5000

Esta é uma preparação real de entrada para os alvos, **não** um desassemblador, recompilador ou runtime. Veja [Preparação de executáveis de Ultra Sun / Ultra Moon](docs/GAME_TARGET_INTAKE.md) para pré-requisitos, formato e limites.

## POC-002 — primeiro subconjunto Thumb-16 → C

Foi adicionada a [POC-002](docs/THUMB_POC_002.md), um tradutor Thumb-16 separado da POC ARM A32. O subconjunto cobre `MOVS`, `ADDS`, `SUBS`, `CMP` imediatos, desvios condicionais EQ..LE, desvio incondicional e `BX LR`. A fixture padrão retorna 7 e NZCV=6; a matriz nativa avalia 224 combinações (14 condições × 16 estados NZCV) contra uma tabela independente. Laços para trás exigem orçamento explícito de execução. Essa é uma segunda prova sintética, não um disassembler ou uma cobertura das instruções dos jogos.

## Inspeção local de um intervalo ARM/Thumb

A ferramenta `tools/inspect_3ds_code_range.py` recebe endereço virtual, estado ARM/Thumb e quantidade explícita de instruções, confere o intervalo contra o `.text` declarado no ExHeader e decodifica os encodings reconhecidos. Por padrão, mantém o modo estrito; `--include-unsupported` registra instruções desconhecidas como encodings brutos sem inventar mnemônicos. O par `BL`/`BLX` imediato do ARMv6K é decodificado como uma chamada de 4 bytes (só cálculo de destino, sem resolver funções); os demais pares Thumb de 32 bits são agrupados numa única entrada bruta, preservando o alinhamento das instruções seguintes, e não existe decoder Thumb-2 completo. Após a inclusão do par BL/BLX, a suíte local tem **203 testes** (inclui BX/BLX Rm, PUSH/POP, POP {..., PC} e LDR literal) e o workflow completo foi aprovado ([run 40193521160](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40193521160)). O relatório com encodings deve permanecer local; use `--report` somente para um caminho fora do repositório. Veja [guia de intervalos locais](docs/CODE_RANGE_INSPECTION.md).

Exemplo (os caminhos e o intervalo abaixo são ilustrativos; confirme antes o estado ARM/Thumb da região local):

    python tools/inspect_3ds_code_range.py --target ultra-sun --exheader /local/exheader.bin --code /local/code.bin --state thumb --start-address 0x00100000 --instruction-count 8 --title-id 00040000001B5000

Esta ferramenta fornece anotação sintática do intervalo, não uma descompilação, código C executável nem prova de equivalência. O ABI real do jogo e o estado de registradores ainda não são modelados.

## Direção do runtime e uso de emuladores

O objetivo é executar o código recompilado em um runtime próprio para Windows, sem depender de um emulador de Nintendo 3DS. Testes do tradutor começam com fixtures sintéticas e resultados esperados a partir da especificação ARM; usar um emulador não é requisito dessa etapa. Se for realmente necessário comparar o comportamento do jogo original no futuro, o Azahar será a referência externa preferida, usada de forma opcional e sem ser incorporada ao runtime ou ao produto final.

## Como acompanhar o progresso

Use GitHub Issues para pesquisas ou problemas com escopo claro. Registre sempre o commit e as versões exatas das ferramentas, comandos executados, resultados observados, logs redigidos e critérios de aceitação. Diferencie resultados reproduzidos de resultados apenas relatados em documentação externa.

Marcos técnicos só podem ser considerados concluídos quando os critérios de aceitação correspondentes em [docs/ROADMAP.md](docs/ROADMAP.md) estiverem demonstrados. Não use percentuais especulativos de conclusão.

## Critérios mínimos de evidência

- **Ferramenta compilada:** o binário da ferramenta foi gerado; isso não demonstra que o jogo foi reconstruído ou executado.
- **Código reconstruído compilado:** uma unidade de código reconstruída foi compilada e sua origem, teste e resultado foram registrados.
- **Executável híbrido:** ainda depende de emulador, intérprete, módulos ou serviços de compatibilidade.
- **Runtime próprio para Windows:** o processo do jogo usa uma camada de runtime de PC identificada e documentada, sem depender de um emulador 3DS para executar os caminhos alegados.
- **Porta nativa de uma parte do jogo:** uma parte delimitada da lógica do jogo funciona no runtime de PC, com recursos de teste permitidos e evidência reproduzível.
- **Jogo completo e estável:** cobertura documentada do jogo-alvo e dos sistemas necessários, com testes de progressão, salvamento, entrada, áudio, gráficos, estabilidade e desempenho em uma matriz explícita de ambientes.

Nenhum desses níveis deve ser inferido apenas a partir de uma captura de tela, de uma compilação bem-sucedida ou de uma porcentagem de instruções recompiladas.
