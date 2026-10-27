# Começar a analisar o código real de Ultra Sun / Ultra Moon

## Escopo e limites

O próximo passo é abrir o executável principal do seu próprio dump em uma ferramenta de engenharia reversa. O script tools/wrap_retail_code.py cria um contêiner ELF32 ARM de análise a partir do ExHeader e do arquivo .code correspondente, já extraído e descomprimido. O ELF preserva o conteúdo original do arquivo de entrada e usa os endereços e alocações dos segmentos declarados no ExHeader.

Este arquivo é apenas um contêiner para análise estática. Não recupera relocations, não identifica funções automaticamente, não prova o verdadeiro ponto de entrada do jogo, não é executado pelo runtime nativo e não significa que Ultra Sun/Ultra Moon já foi recompilado. O endereço ELF entry é apenas uma dica na base declarada de .text.

## 1. Prepare arquivos locais que correspondam entre si

Use apenas arquivos de jogo que você possui e está autorizado a analisar. Extraia o ExHeader e o arquivo .code do mesmo executável, com uma ferramenta local apropriada para 3DS. O [Project_CTR / ctrtool](https://github.com/3DSGuy/Project_CTR) é uma referência pública de ferramentas para esses contêineres; este repositório não extrai, decifra nem descomprime a ROM.

Mantenha jogo base e atualização separados. O arquivo .code informado deve estar realmente descomprimido. O ExHeader registra se o arquivo originalmente guardado no ExeFS era comprimido, mas a flag não prova se a entrada fornecida ao script já foi descomprimida. A opção --confirm-decompressed é uma confirmação do mantenedor e não descomprime os bytes.

Primeiro rode o preflight existente:

    python tools/inspect_3ds_target.py --target ultra-sun --exheader "C:/local/exheader.bin" --code "C:/local/code.bin" --title-id 00040000001B5000

Para Ultra Moon, troque o alvo para ultra-moon e use arquivos compatíveis entre si. O title ID do contêiner é separado do Program ID no ACI do ExHeader. Um tamanho conhecido é apenas uma pista e não comprova a revisão exata.

## 2. Criar um ELF de análise

Salve o ELF e o relatório fora do repositório, pois o ELF inclui os bytes do jogo:

    python tools/wrap_retail_code.py --target ultra-sun --exheader "C:/local/exheader.bin" --code "C:/local/code.bin" --confirm-decompressed --output "C:/local-analysis/ultra-sun-analysis.elf" --report "C:/local-analysis/ultra-sun-analysis.json"

No Linux/WSL use caminhos locais equivalentes. Um Program ID desconhecido é recusado por padrão. Só utilize --allow-unverified-target após investigar manualmente a divergência. A ferramenta também recusa sobrescrever o ExHeader ou o .code e não permite escrever o ELF ou o relatório dentro da árvore do projeto.

O JSON registra os hashes SHA-256, alocações e endereços virtuais, avisos e a confirmação de que os segmentos de arquivo no ELF preservam os bytes da entrada. A saída precisa permanecer privada e não deve ser enviada ao GitHub ou aos workflows.

## 3. Encontrar uma primeira função real

Abra o ELF no Ghidra ou configure localmente uma ferramenta compatível. Comece por uma função pequena e isolada. Confirme independentemente endereço, limite, estado ARM/Thumb, pools de literais, fluxo de controle, chamadas e referências; um decodificador independente como Capstone pode ajudar a conferir a decodificação. Não trate uma varredura linear de toda a região .text como código, pois ela pode conter dados e literais.

Registre localmente o alvo e a revisão declarados, hashes, endereço virtual, estado de instrução, limites aceitos, chamadas, referências, entradas/saídas e efeitos observáveis. Só depois escolha uma sequência real controlada e expanda o tradutor para os encodings observados. A primeira meta é traduzir uma função real pequena com limites e semântica verificados de forma independente e, então, comparar a função reconstruída como C compilado nativamente. Ainda não há uma função real do jogo validada neste repositório.

## 4. Arquivos privados

Não envie ROMs, CIA/3DS/CXI, .code, ExHeader, ELF gerado, recursos extraídos, chaves ou relatórios brutos de desassemblagem para commits, issues, releases, GitHub Pages, CI ou artefatos. As regras de .gitignore ajudam, mas não substituem a conferência manual do conteúdo e do estado do Git.

Referências técnicas: [3dbrew — ExeFS](https://www.3dbrew.org/wiki/ExeFS), [3dbrew — NCCH Extended Header](https://www.3dbrew.org/wiki/NCCH/Extended_Header), [Project_CTR / ctrtool](https://github.com/3DSGuy/Project_CTR) e [REA](https://github.com/morluto/rea). A análise estática revela instruções, pseudocódigo e referências, mas não recupera automaticamente o código-fonte original. Correspondência de compilador, relocations, módulos dinâmicos CRO, serviços do 3DS e gameplay continuam sendo tarefas separadas. Ultra Sun e Ultra Moon precisam ser verificadas individualmente.
