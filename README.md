# PokeUltrarecomp

**Estado: fase inicial de pesquisa, documentação, auditoria e ferramentas de verificação do repositório.** Este repositório ainda não contém uma porta funcional de Pokémon Ultra Sun ou Pokémon Ultra Moon, um runtime próprio para Windows, nem resultados de compilação da porta ou testes de jogo executados por este projeto.

## Objetivo

Investigar uma possível porta para Windows de **Pokémon Ultra Sun** e **Pokémon Ultra Moon**, preservando tanto quanto legalmente permitido a lógica e o comportamento dos jogos e estudando como substituir os serviços específicos do Nintendo 3DS por implementações para PC.

A estratégia inicial é estudar projetos de reconstrução, descompilação, recompilação e emulação existentes, aproveitar apenas resultados tecnicamente demonstrados e evitar reescritas desnecessárias. A existência de um emulador, de código C/C++ gerado ou de uma cena inicial funcional não prova, por si só, que um jogo foi portado nativamente.

## Estado atual verificável

- O trabalho deste repositório está limitado à organização, documentação, pesquisa inicial e ferramentas locais de proteção/verificação; o runtime do jogo ainda não foi implementado.
- Este conjunto de documentos registra uma auditoria documental dos quatro projetos de referência listados abaixo. Os testes reportados por esses projetos foram lidos em suas documentações, mas **não foram executados independentemente por este repositório**.
- Ainda não há runtime próprio implementado aqui, prova de conceito compilada, teste de jogo reproduzível ou porta nativa funcional reivindicada.
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

É necessário Python 3.10 ou mais recente e Git. O verificador analisa arquivos no índice Git e arquivos não ignorados que ainda não foram rastreados. Ele não examina o histórico inteiro, arquivos ignorados não rastreados, o conteúdo semântico de cada arquivo ou a situação jurídica das fontes. Não substitui revisão do diff, nem comprova que a porta funciona. O uso de `.gitignore` continua sendo uma barreira adicional, não uma garantia.

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
