# Preparação de executáveis de Ultra Sun / Ultra Moon

## Escopo desta etapa

Esta etapa começa a atuar nos alvos dos jogos, sem fingir que a recompilação já existe. A ferramenta `tools/inspect_3ds_target.py` confere metadados do ExHeader e a estrutura de um `.code` já extraído e descomprimido localmente. Não abre um `.3ds`/`.cia`, não decifra, não descomprime, não decodifica instruções, não produz C do jogo e não necessita de emulador.

A estrutura relevante é `NCCH/CXI → ExeFS/.code`. O ExHeader descreve os endereços virtuais, quantidade de páginas e tamanhos dos segmentos `.text`, `.rodata` e `.data`, além do tamanho de stack e BSS. A documentação pública do formato está em [3dbrew — ExeFS](https://www.3dbrew.org/wiki/ExeFS) e [3dbrew — NCCH Extended Header](https://3dbrew.org/wiki/NCCH/Extended_Header). O projeto [3dsrecomp](https://github.com/fearkov/3dsrecomp) explica por que um recompilador 3DS precisa analisar ARM/Thumb e também módulos dinâmicos.

## Perfis de alvo

| Perfil | Title ID base conhecido | Title ID de atualização conhecido |
| --- | --- | --- |
| `ultra-sun` | `00040000001B5000` | `0004000E001B5000` |
| `ultra-moon` | `00040000001B5100` | `0004000E001B5100` |

Esses identificadores servem para evitar misturar os dois executáveis; não provam sozinhos a revisão exata do conteúdo local. Um ID desconhecido é relatado como não verificado, e um ID conhecido do outro jogo é recusado. O catálogo de IDs dos perfis deve ser ampliado só com evidência para uma variante nova. A referência técnica usada para os identificadores inclui [3DSDB](https://www.3dsdb.com/) e os manifestos públicos de projetos comunitários; os perfis não contêm bytes, hashes conhecidos de dumps, assets ou código dos jogos.

## Pré-requisitos da entrada local

O mantenedor precisa fornecer, fora do Git, um ExHeader extraído do mesmo executável e o arquivo `.code` correspondente **já descomprimido**. Caso a flag `CompressExefsCode` do ExHeader esteja ativa, isso significa que o `.code` armazenado no ExeFS original era comprimido; esta ferramenta não descomprime nem tenta adivinhar o estado dos dados. Use ferramentas de análise local adequadas ao seu próprio dump e confirme a saída antes de continuar.

O `.code` de Ultra Sun não deve ser trocado pelo de Ultra Moon. A versão do jogo/atualização também importa: este preflight registra tamanho e SHA-256, mas ainda não valida a revisão exata nem aplica regras de equivalência entre revisões.

## Uso

    python tools/inspect_3ds_target.py --target ultra-sun --exheader /caminho/local/exheader.bin --code /caminho/local/code.bin --title-id 00040000001B5000

Para Ultra Moon, troque o perfil por `ultra-moon` e indique entradas locais correspondentes ao mesmo executável. `--title-id` é opcional; sem ele, o relatório deixa claro que a identidade escolhida foi declarada pelo usuário e não verificada. Um ID reconhecido como pertencente ao outro jogo causa erro. Um ID ainda não conhecido é marcado como não verificado, não é adivinhado.

Por padrão, o programa imprime JSON no terminal. Para salvar um relatório, use `--report /caminho/fora/do/repositorio/report.json`. O relatório contém nomes de arquivo, tamanho e SHA-256, não o conteúdo do `.code` ou o caminho absoluto local. Ainda assim, mantenha o relatório local: o hash pode identificar uma entrada privada ou uma revisão de jogo e não precisa ser publicado.

## O que é verificado

- O ExHeader tem pelo menos a área SCI de `0x200` bytes.
- Cada segmento respeita seu número de páginas e não se sobrepõe ao intervalo virtual de outro segmento.
- O endereço não ultrapassa o espaço de 32 bits e possíveis desalinhamentos de página são avisados.
- O tamanho do `.code` é suficiente para os tamanhos declarados e não excede a capacidade total de páginas. Se o comprimento não coincidir com a capacidade total, o relatório avisa que o layout precisa ser revisto.
- A identificação de título é marcada como correspondida, não reconhecida ou ausente; um ID conhecido do jogo oposto é recusado.
- SHA-256 do ExHeader e do `.code` são calculados para que o mantenedor possa registrar a sua entrada local sem distribuí-la.

## Limites e próximo marco

**Passar neste preflight não prova que o arquivo é autêntico, que os bytes são código em todas as regiões, que os limites ARM/Thumb foram encontrados corretamente ou que o jogo pode ser recompilado.** Não há desassemblagem, descoberta de funções, relocations, CRO, interpretação, runtime Windows, gráficos ou gameplay nesta ferramenta.

O próximo marco é fazer um inventário de segmentos e instruções com análise específica ARM/Thumb e fixtures conhecidas, depois selecionar uma unidade pequena cuja semântica possa ser comparada de modo reproduzível. CROs e recursos de RomFS devem ser catalogados separadamente; não presumir que a análise do executável principal cobre módulos dinâmicos. Dados reais do jogo permanecem no computador do mantenedor e nunca são anexados aos testes ou commits.
