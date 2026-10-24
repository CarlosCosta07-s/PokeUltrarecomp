# Avisos de terceiros

Este registro é um inventário inicial de fontes consultadas, não uma lista de dependências incorporadas. Nenhum código de referência foi copiado como parte desta organização documental.

| Componente/projeto | Origem | Commit consultado | Licença/estado observado | Atribuições e alterações | Uso no PokeUltrarecomp |
| --- | --- | --- | --- | --- | --- |
| UltraSunnyMoon | [GitHub](https://github.com/tylergraydev/UltraSunnyMoon) | [913eed4969163ea15e354dacb8e2bfe0a2439de5](https://github.com/tylergraydev/UltraSunnyMoon/commit/913eed4969163ea15e354dacb8e2bfe0a2439de5) | LICENSE não encontrado no caminho padrão consultado; permissão incerta | Não aplicável; nada copiado | Referência documental somente |
| 3dsrecomp | [GitHub](https://github.com/fearkov/3dsrecomp) | [c3f21f94ba50d688025febc8974ff348d471b587](https://github.com/fearkov/3dsrecomp/commit/c3f21f94ba50d688025febc8974ff348d471b587) | Cargo.toml declara MIT; LICENSE não encontrado no caminho padrão consultado; confirmação pendente | Antes de incorporar, obter confirmação do texto aplicável e preservar atribuições MIT | Referência documental somente |
| Zakuro | [GitHub](https://github.com/fearkov/zakuro) | [70b56de5a17eca8b3fa9316b31e24ac9eacd8f96](https://github.com/fearkov/zakuro/commit/70b56de5a17eca8b3fa9316b31e24ac9eacd8f96) | MIT; arquivo LICENSE encontrado (SHA consultado: b028942e512fab6d9a85583b7a2444972f022f60) | A licença exige preservar copyright e permissão; nenhuma alteração ou cópia neste repositório | Referência documental somente |
| PokéMoon | [GitHub](https://github.com/gradenGnostic/pokemoon) | [7a5936eee5d08889d6cc534e6916a86b39fde694](https://github.com/gradenGnostic/pokemoon/commit/7a5936eee5d08889d6cc534e6916a86b39fde694) | LICENSE não encontrado no caminho padrão consultado; README não declara licença geral; confirmação pendente | Revisar cabeçalhos e obter permissão antes de reutilizar | Referência documental somente |
| 3DS Decomp Pipeline | [GitHub](https://github.com/AlgebraManiacABC/3DS-Decomp-Pipeline) | Commit citado por PokéMoon: 621bbce909ad2f9c551563c7443ed80c0123fe77 | Não auditado diretamente nesta etapa | Não incorporado; revisar licença e origem se for considerado | Referência transitiva mencionada por documentação de terceiro |

## Dependências de runtime citadas nas referências

| Dependência | Fonte da menção | Licença/versão verificada aqui | Estado |
| --- | --- | --- | --- |
| SDL2 | CMakeLists de PokéMoon | Não verificada neste trabalho | Não incorporada |
| OpenGL | CMakeLists de PokéMoon | API/driver de plataforma; versão e dependências do alvo não verificadas | Não incorporada |
| Rust e compilador C/C++ | READMEs/Cargo manifests das referências | Versões requeridas por ferramenta variam; não são dependências atuais deste repositório | Não instaladas por este trabalho |
| REA, Ghidra, CTRTool e outros instrumentos de análise | Documentação de UltraSunnyMoon | Não auditados como dependências a serem incorporadas | Não incorporados |

## Procedimento para novos componentes

Antes de incorporar, registrar: nome e função, origem oficial, commit/tag/hash, autores/copyright, arquivo e versão da licença, compatibilidade com as outras licenças, dependências transitivas, avisos obrigatórios, modificações locais, testes e se algum output pode derivar de dados proprietários.

A licença de uma ferramenta não licencia ROMs, dumps, firmware, jogos, assets ou resultados derivados. Não assumir que outputs gerados são redistribuíveis. Rever este inventário em cada atualização de dependência.
