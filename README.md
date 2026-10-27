# PokeUltrarecomp

**Pesquisa para uma porta nativa de Pokémon Ultra Sun e Pokémon Ultra Moon para Windows/Linux.**  
**Estado real:** ferramentas de inspeção estática e provas de conceito sintéticas estão publicadas; ainda não existe uma porta jogável nem um runtime de jogo funcional.

## Direção do projeto

O objetivo é executar o jogo como uma aplicação nativa de PC, e não através de emulação de Nintendo 3DS ou interpretação de instruções.

- **C++20:** runtime nativo, ABI, memória, serviços de plataforma e integração.
- **C gerado:** resultado da recompilação estática ARM/Thumb, compilado pelo toolchain nativo do sistema.
- **SDL3:** janela, teclado, controles e áudio multiplataforma.
- **Vulkan:** renderização de PC por drivers nativos, sem criar uma GPU virtual do 3DS.
- **Python:** ferramentas de análise, geração auxiliar e testes de desenvolvimento; não será dependência de execução do jogo.
- **Windows/Linux x86-64:** primeiros alvos. CMake + Ninja organizarão o build; MSVC no Windows e GCC/Clang no Linux.

A engine será um runtime próprio em C++ sobre SDL3 e Vulkan. Godot, Unity e Unreal não foram escolhidas como base: nenhuma recompila por si só o código ARM/Thumb do jogo nem resolve o ABI, os módulos e os serviços de sistema que esse código exige.

**Restrições obrigatórias:** sem emulador, interpretação ARM/Thumb, JIT ou fallback interpretado. Código não suportado deve bloquear a tradução/execução do caminho correspondente. A prioridade é primeiro obter execução funcional; otimização de desempenho vem depois.

A escolha de SDL3/Vulkan é arquitetural, ainda não uma dependência já integrada ao build. A versão inicial do SDL a avaliar e fixar é 3.4.18. Veja as [decisões e marcos técnicos](docs/NATIVE_PORT_DIRECTION.md) e a [arquitetura do runtime](docs/ARCHITECTURE.md).

## O que existe hoje

- **POC-001 ARM A32 → C:** tradutor experimental de um subconjunto sintético, com operações aritméticas/lógicas limitadas, predicação e flags NZCV. Não é um recompilador ARM geral. [Especificação e limites](docs/POC_001_SPEC.md).
- **POC-002 Thumb-16 → C:** tradutor experimental de um subconjunto Thumb-16 sintético. Não cobre todas as instruções usadas pelo jogo. [Especificação](docs/THUMB_POC_002.md).
- **Intake do alvo:** perfis de Ultra Sun/Ultra Moon e verificação de metadados/segmentos em entradas locais. [Guia](docs/GAME_TARGET_INTAKE.md).
- **Inspeção de código:** inspeção explícita de intervalos ARM/Thumb e anotações conservadoras de fluxo de controle, memória e efeitos de registradores. [Guia](docs/CODE_RANGE_INSPECTION.md).
- **Contrato de função candidata:** validador estático para comparar efeitos observados com um contrato declarado. Ele não prova equivalência. [Guia](docs/FUNCTION_CONTRACT.md).
- **Pesquisa e auditoria de referências:** fontes consultadas e limitações de reutilização. [Pesquisa técnica](docs/CODEBASE_RESEARCH.md) e [auditoria](docs/AUDIT.md).
- **Pipeline nativo sintético:** `tools/run_native_poc_pipeline.py` traduz fixtures A32/Thumb para C, compila os binários do host e confere resultado, registradores, flags e orçamento de execução.
- **Memória Thumb limitada:** uma opção experimental do tradutor gera loads/stores C nativos para uma lista explícita de instruções Thumb-1, usando uma região sintética de memória com limites, alinhamento e estados de falha verificados. Não é a memória real dos jogos e não adiciona fallback interpretado.
- **Fronteira C/C++ nativa:** [`native_abi.h`](include/pokeultrarecomp/native_abi.h), gerador de fixtures e [host de teste C++20](tests/native_runtime_host.cpp). O C gerado é compilado como C; um host C++ chama as funções pela ABI versionada e verifica rejeição de entradas inválidas sem modificar parcialmente a saída. Isso é uma prova de integração, não ainda a ABI final de gameplay.

As POCs testam fixtures sintéticas e partes de código C gerado. A versão com o modelo de memória limitado passou no [workflow nativo #40443261093](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443547298): **4/4 testes CTest em Linux/GCC e Windows/MSVC**, incluindo recompilação/execução nativa, ABI C/C++20, suíte Python e segurança do repositório. A suíte independente passou em **325 testes** no [workflow #40443261098](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443547245). O teste novo cobre as 14 formas de load/store que o modo experimental aceita (por registrador e por imediato, 8/16/32 bits, incluindo LDRSB/LDRSH), além de extensão de sinal, limites, alinhamento, mapeamento inválido e ausência de escrita parcial. Tudo usa apenas fixtures sintéticas: nenhum arquivo real de Ultra Sun/Ultra Moon foi validado e nenhum jogo foi iniciado pelo runtime. Os resultados **não provam que o jogo funciona**.

## Próximos marcos

1. **N1 — Pipeline nativo:** recompilar uma sequência sintética em C, compilar e executar como binário nativo no Windows e no Linux, com oráculo independente e sem fallback para interpretação.
2. **N2 — Primeira função real:** selecionar localmente uma função autorizada, confirmar estado ARM/Thumb e contrato, recompilar e validar os efeitos observáveis sem publicar bytes nem relatórios proprietários.
3. **N3 — Primeiro caminho do jogo:** ligar unidades reais ao runtime C++ e implementar apenas os serviços comprovadamente necessários ao primeiro caminho funcional.
4. Depois: ampliar gráficos, áudio, entrada, salvamentos, progressão e estabilidade. Medir e otimizar desempenho somente após existir um caminho real de execução.
5. Validar Ultra Moon separadamente; não presumir compatibilidade total com base em Ultra Sun.

O roteiro detalhado e os critérios de conclusão estão em [docs/ROADMAP.md](docs/ROADMAP.md).

## Testes e desenvolvimento local

Requisitos atuais das ferramentas Python: Python 3.10+ e Git. Na raiz do repositório, os comandos documentados incluem:

    cmake -S . -B build -G Ninja
    cmake --build build --target verify

    python tools/run_native_poc_pipeline.py
    python tools/arm_subset_poc.py
    python tools/arm_differential_poc.py
    python -m unittest discover -s tests -v
    python tools/check_repository_safety.py

A cobertura de cada ferramenta está descrita na respectiva documentação. O tradutor deve falhar de forma explícita para instruções não suportadas. O verificador de segurança ajuda a detectar caminhos/arquivos suspeitos e links Markdown quebrados, mas não examina o histórico inteiro, conteúdo semântico de todo binário nem questões jurídicas. O uso de .gitignore não é uma garantia.

O smoke test em `tools/run_native_poc_pipeline.py` traduz fixtures sintéticas A32/Thumb, compila C gerado pelo compilador do host e executa binários nativos. Para Thumb, o modo Python opcional `runtime_memory_io=True` emite acessos C nativos a uma região guest byte-array limitada, com verificações de faixa/alinhamento e códigos de falha. O workflow `native-pipeline.yml` é executado no Windows e Linux através de CMake/Ninja/CTest. No [workflow #40443261093](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443547298), os dois jobs aprovaram os quatro testes CTest; a suíte Python passou com 325 testes no [workflow #40443261098](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40443547245). O modo de memória cobre apenas instruções explicitamente listadas e não modela a memória real, PC/SP, stack, memória mapeada do jogo ou a semântica completa da CPU ARM11. `CMakeLists.txt` configura C11/C++20 e o alvo `verify`; SDL3/Vulkan ainda não estão integrados ao runtime do jogo.

## Uso de entradas locais e propriedade intelectual

Não adicionar a commits, issues, pull requests, releases, GitHub Pages, CI ou artefatos:
- ROMs, dumps, firmware, chaves ou executáveis dos jogos;
- modelos, texturas, mapas, sons, músicas, fontes ou quaisquer recursos proprietários extraídos;
- código ou arquivos derivados de entradas proprietárias sem direitos de distribuição verificados;
- tokens, credenciais, caminhos pessoais ou relatórios sensíveis.

A documentação de entrada local destina-se apenas ao ambiente do mantenedor. Não presumimos que possuir uma cópia do jogo autorize automaticamente extração, modificação, recompilação ou distribuição. Leia [docs/LEGAL_AND_IP.md](docs/LEGAL_AND_IP.md) antes de qualquer trabalho que dependa de arquivos do jogo.

O arquivo LICENSE preexistente necessita de revisão de procedência e abrangência; não o interprete como autorização para licenciar código ou recursos de terceiros. Veja também [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Independência

PokeUltrarecomp é um projeto independente de pesquisa e fãs. Não é afiliado, patrocinado, autorizado ou endossado pela Nintendo, GAME FREAK, Creatures Inc. ou The Pokémon Company. Pokémon e os títulos dos jogos pertencem aos respectivos titulares. Este aviso não concede direitos nem garante imunidade contra reclamações.
