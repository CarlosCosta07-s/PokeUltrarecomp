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

As POCs testam fixtures sintéticas e partes de código C gerado. Nenhum arquivo real de código de Ultra Sun/Ultra Moon foi validado pela CI descrita aqui; nenhum jogo foi iniciado pelo runtime deste projeto. Os resultados históricos publicados estão ligados a commits e workflows específicos e **não devem ser interpretados como prova de que o jogo funciona**.

## Próximos marcos

1. **N1 — Pipeline nativo:** recompilar uma sequência sintética em C, compilar e executar como binário nativo no Windows e no Linux, com oráculo independente e sem fallback para interpretação.
2. **N2 — Primeira função real:** selecionar localmente uma função autorizada, confirmar estado ARM/Thumb e contrato, recompilar e validar os efeitos observáveis sem publicar bytes nem relatórios proprietários.
3. **N3 — Primeiro caminho do jogo:** ligar unidades reais ao runtime C++ e implementar apenas os serviços comprovadamente necessários ao primeiro caminho funcional.
4. Depois: ampliar gráficos, áudio, entrada, salvamentos, progressão e estabilidade. Medir e otimizar desempenho somente após existir um caminho real de execução.
5. Validar Ultra Moon separadamente; não presumir compatibilidade total com base em Ultra Sun.

O roteiro detalhado e os critérios de conclusão estão em [docs/ROADMAP.md](docs/ROADMAP.md).

## Testes e desenvolvimento local

Requisitos atuais das ferramentas Python: Python 3.10+ e Git. Na raiz do repositório, os comandos documentados incluem:

    python tools/arm_subset_poc.py
    python tools/arm_differential_poc.py
    python -m unittest discover -s tests -v
    python tools/check_repository_safety.py

A cobertura de cada ferramenta está descrita na respectiva documentação. O tradutor deve falhar de forma explícita para instruções não suportadas. O verificador de segurança ajuda a detectar caminhos/arquivos suspeitos e links Markdown quebrados, mas não examina o histórico inteiro, conteúdo semântico de todo binário nem questões jurídicas. O uso de .gitignore não é uma garantia.

O pipeline CMake/Ninja com SDL3/Vulkan será introduzido como parte do marco N1 e deverá ser validado em Windows e Linux antes de ser considerado concluído. Não alegamos que o build nativo integrado já exista.

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
