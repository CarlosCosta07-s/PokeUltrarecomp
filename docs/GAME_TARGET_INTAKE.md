# Preparação de executáveis de Ultra Sun / Ultra Moon

## Escopo desta etapa

Esta etapa começa a atuar nos alvos dos jogos, sem fingir que a recompilação já existe. A ferramenta `tools/inspect_3ds_target.py` confere metadados do ExHeader e a estrutura de um `.code` já extraído e descomprimido localmente. Não abre um `.3ds`/`.cia`, não decifra, não descomprime, não decodifica instruções, não produz C do jogo e não necessita de emulador.

A estrutura relevante é `NCCH/CXI → ExeFS/.code`. O ExHeader contém o SCI na faixa `0x000..0x1FF` e o ACI a partir de `0x200`; o ID do programa de 64 bits está no início do ACI (`0x200..0x207`). O inspetor exige pelo menos `0x208` bytes para não identificar um alvo usando apenas o SCI. O SCI descreve os endereços virtuais, quantidade de páginas e tamanhos dos segmentos `.text`, `.rodata` e `.data`, além do tamanho de stack e BSS. A documentação pública do formato está em [3dbrew — ExeFS](https://www.3dbrew.org/wiki/ExeFS) e [3dbrew — NCCH Extended Header](https://3dbrew.org/wiki/NCCH/Extended_Header). O projeto [3dsrecomp](https://github.com/fearkov/3dsrecomp) explica por que um recompilador 3DS precisa analisar ARM/Thumb e também módulos dinâmicos.

## Perfis de alvo

| Perfil | Title ID base conhecido | Title ID de atualização conhecido |
| --- | --- | --- |
| `ultra-sun` | `00040000001B5000` | `0004000E001B5000` |
| `ultra-moon` | `00040000001B5100` | `0004000E001B5100` |

O inspetor compara o Program ID embutido no ACI com a lista de IDs dos dois perfis e rejeita um ID conhecido do jogo oposto. O `--title-id` opcional é uma declaração separada sobre o contêiner NCCH; não substitui o Program ID lido do ExHeader. Um ID desconhecido é relatado como não verificado. Esses identificadores não provam sozinhos a revisão exata do conteúdo local. O catálogo de IDs dos perfis deve ser ampliado só com evidência para uma variante nova. A referência técnica usada para os identificadores inclui [3DSDB](https://www.3dsdb.com/) e os manifestos públicos de projetos comunitários; os perfis não contêm bytes, hashes conhecidos de dumps, assets ou código dos jogos.

## Pré-requisitos da entrada local

O mantenedor precisa fornecer, fora do Git, um ExHeader extraído do mesmo executável e o arquivo `.code` correspondente **já descomprimido**. Caso a flag `CompressExefsCode` do ExHeader esteja ativa, isso significa que o `.code` armazenado no ExeFS original era comprimido; esta ferramenta não descomprime nem tenta adivinhar o estado dos dados. Use ferramentas de análise local adequadas ao seu próprio dump e confirme a saída antes de continuar.

O `.code` de Ultra Sun não deve ser trocado pelo de Ultra Moon. A versão do jogo/atualização também importa: este preflight registra tamanho e SHA-256, mas ainda não valida a revisão exata nem aplica regras de equivalência entre revisões.

## Uso

    python tools/inspect_3ds_target.py --target ultra-sun --exheader /caminho/local/exheader.bin --code /caminho/local/code.bin --title-id 00040000001B5000

Para Ultra Moon, troque o perfil por `ultra-moon` e indique entradas locais correspondentes ao mesmo executável. `--title-id` é opcional e é registrado separadamente do Program ID lido do ACI; sem ele, o relatório avisa que a identidade do contêiner/base/atualização ainda pode ser ambígua. Um ID reconhecido como pertencente ao outro jogo causa erro. Um ID ainda não conhecido é marcado como não verificado, não é adivinhado.

Por padrão, o programa imprime JSON no terminal. Para salvar um relatório, use `--report /caminho/fora/do/repositorio/report.json`. O relatório contém nomes de arquivo, tamanho e SHA-256, não o conteúdo do `.code` ou o caminho absoluto local. Também informa o Program ID do ACI e o offset de cada segmento no `.code` já descomprimido. Ainda assim, mantenha o relatório local: o hash pode identificar uma entrada privada ou uma revisão de jogo e não precisa ser publicado.

## O que é verificado

- O ExHeader tem pelo menos `0x208` bytes: a área SCI de `0x200` bytes e os 8 bytes do Program ID no início do ACI.
- Cada segmento respeita seu número de páginas e não se sobrepõe ao intervalo virtual de outro segmento.
- O endereço não ultrapassa o espaço de 32 bits e possíveis desalinhamentos de página são avisados.
- O `.code` já descomprimido precisa ter exatamente o tamanho da soma das alocações page-padded declaradas no ExHeader. Cada segmento recebe um `code_file_offset` (`text`, depois `rodata`, depois `data`) para orientar o próximo passo de análise; layouts com comprimento diferente são rejeitados, não aceitos com aviso.
- A identificação de título é marcada como correspondida, não reconhecida ou ausente; um ID conhecido do jogo oposto é recusado.
- SHA-256 do ExHeader e do `.code` são calculados para que o mantenedor possa registrar a sua entrada local sem distribuí-la.

## Limites e próximo marco

**Passar neste preflight não prova que o arquivo é autêntico, que os bytes são código em todas as regiões, que os limites ARM/Thumb foram encontrados corretamente ou que o jogo pode ser recompilado.** Não há desassemblagem, descoberta de funções, relocations, CRO, interpretação, runtime Windows, gráficos ou gameplay nesta ferramenta.

O próximo marco é fazer um inventário de segmentos e instruções com análise específica ARM/Thumb e fixtures conhecidas, depois selecionar uma unidade pequena cuja semântica possa ser comparada de modo reproduzível. CROs e recursos de RomFS devem ser catalogados separadamente; não presumir que a análise do executável principal cobre módulos dinâmicos. Dados reais do jogo permanecem no computador do mantenedor e nunca são anexados aos testes ou commits.

## ELF local para ferramentas de análise

O preflight não produz um binário de análise. Para converter o `.code` descomprimido em um ELF32 ARM que preserve os endereços virtuais declarados no ExHeader, consulte [o fluxo de análise de código real](REAL_GAME_CODE_WORKFLOW.md). O ELF e o relatório contêm dados derivados do jogo e devem permanecer fora do repositório. Esta etapa apenas permite abrir a imagem em Ghidra/REA; não descobre funções, recompila o jogo ou prova funcionamento.

## Inspeção sintática de um intervalo selecionado

Depois de conferir o ExHeader e o `.code` com `tools/inspect_3ds_target.py`, é possível pedir a anotação sintática de uma faixa explicitamente escolhida com `tools/inspect_3ds_code_range.py`. O endereço virtual, o estado ARM/Thumb e a quantidade são obrigatórios; a ferramenta não tenta descobrir limites de função nem adivinhar o estado de instrução. Consulte [CODE_RANGE_INSPECTION.md](CODE_RANGE_INSPECTION.md).


## Download remoto privado e fallback

A ingestão remota usa a secret `POKEULTRARECOMP_SOURCE_URL` como origem principal. Se esse provedor bloquear o download por quota/rate-limit, a secret opcional `POKEULTRARECOMP_SOURCE_URL_FALLBACK` permite indicar outra origem HTTPS autorizada para a mesma imagem. O fallback só é tentado quando o erro da origem principal é classificado como quota/rate-limit; permissões, formato inválido e outros erros não são mascarados por uma segunda tentativa. As duas origens passam pela mesma política HTTPS e pelo limite de 8 GiB. O resumo da execução registra somente se o fallback foi utilizado, nunca a URL.

Configure a secret em **Settings → Secrets and variables → Actions** do repositório. Não publique URLs privadas em commits, issues, logs ou documentação. A ROM, o código extraído, hashes privados e desassemblagem não são enviados como artefatos. Sem uma segunda origem configurada, o comportamento continua seguro e explícito: uma quota do Google Drive interrompe a ingestão antes de a análise começar.
