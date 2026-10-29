# Analisar uma imagem de Nintendo 3DS sem anexá-la ao chat

## Formatos aceitos

O workflow remoto aceita .3ds, .cci e .cia. CTRTool documenta .3ds/.cci como variantes da imagem de cartucho NCSD e .cia como arquivo de instalação. .ccd não é um formato de imagem de jogo Nintendo 3DS; confira a extensão real do arquivo se esse era o formato pretendido. Este workflow não aceita .ccd.

Referências técnicas:
- CTRTool README: https://github.com/3DSGuy/Project_CTR/blob/master/ctrtool/README.md
- CTRTool releases: https://github.com/3DSGuy/Project_CTR/releases

## Executar pelo GitHub no navegador ou celular

**Limite importante sobre anexos do ChatGPT:** os arquivos anexados a uma conversa não são transferidos automaticamente para o runner do GitHub Actions. Este workflow só lê o arquivo disponível por meio da URL HTTPS guardada em `POKEULTRARECOMP_SOURCE_URL` (e, em caso de quota/limitação, a URL de fallback autorizada). Portanto, uma execução bem-sucedida não significa que as partes anexadas ao chat foram usadas. Para usar um arquivo dividido, mantenha todas as partes juntas e extraia o `.cia`, `.cci` ou `.3ds`; para intake remoto, coloque o arquivo final num host de download HTTPS autorizado e configure o secret, ou execute a ferramenta localmente. Não envie a imagem ao Git, issues, releases ou artifacts.

Este modo permite processar a imagem em um runner temporário do GitHub Actions sem executar as ferramentas no seu computador. O workflow aceita uma URL HTTPS de download direto e links de compartilhamento de arquivos do Google Drive. Para o Drive, utiliza gdown 6.4.2 para resolver as confirmações de arquivo grande e transferir a imagem; o arquivo precisa permitir acesso a quem possui o link. A URL nunca deve ser colocada no código, em uma issue ou na linha de comando de um workflow. Arquivos que exigem login, que excederam a cota de download do Drive ou que estão bloqueados pelo provedor ainda podem falhar. As mensagens de falha são reduzidas a categorias seguras (cota/limitação temporária, permissão/link ou rede); texto bruto de respostas e URLs privadas não são publicados nos logs.

1. No repositório, abra Settings, depois Secrets and variables, depois Actions. Crie o secret POKEULTRARECOMP_SOURCE_URL com a URL HTTPS de download direto. Use um link restrito/temporário se o seu provedor permitir.
2. Abra Actions, selecione Remote Nintendo 3DS container intake e toque em Run workflow.
3. Escolha ultra-sun ou ultra-moon, selecione 3ds, cci ou cia e informe o índice da partição/conteúdo (normalmente 0).
4. Consulte o resumo do job. Além da extração e da validação estrutural, para `.3ds/.cci` o workflow compara o Program ID do cabeçalho NCCH selecionado com o perfil do jogo, inclusive distinguindo base/atualização quando conhecido. Para `.cia`, a ferramenta lê o Title ID a partir de um TMD RSA-2048/SHA-256 v1, conferindo limites de seção, versão e tipo de título, exigindo pelo menos um registro e verificando se o tamanho declarado comporta a quantidade de registros de conteúdo do TMD antes da comparação. Essa leitura é estrutural: não verifica a assinatura criptográfica, não autentica o arquivo nem identifica a revisão exata. O job contabiliza padrões de prólogo ARM/Thumb, candidatos que chegam linearmente a um retorno comum e um censo agregado do Ghidra. A versão atual também seleciona, em armazenamento temporário, corpos candidatos A32 pequenos para tentar o tradutor atual e compilar amostras C apenas em modo de verificação de sintaxe; o resumo pode contar as famílias de instruções que faltam. Endereços, palavras, C gerado, logs detalhados e ROM não são publicados. Isso não confirma uma revisão exata, limites de função ou equivalência semântica.

O workflow tem limite de download de 8 GiB, limite de execução de 120 minutos, usa CTRTool v1.3.0 e fixa gdown em 6.4.2 para baixar arquivos públicos do Google Drive. Para a análise estática agregada, instala Java 25 (requisito do Ghidra 12.2) e baixa Ghidra 12.2 do release oficial, verificando o SHA-256 do arquivo ZIP antes de executar o analisador headless. Se a imagem exigir chaves que o workflow não tem ou não puder ser extraída diretamente, ele falha de forma explícita; não tenta recuperar chaves ou contornar criptografia.

## Executar localmente sem enviar a imagem à nuvem

O modo `tools/local_3ds_intake.py` é a alternativa ao workflow remoto quando um provedor limita downloads, quando você prefere não transferir a imagem para GitHub Actions ou quando quer inspecionar o conteúdo diretamente no computador. Ele não baixa a imagem, não precisa das secrets `POKEULTRARECOMP_SOURCE_URL*` e não faz upload de ROM, código extraído, hashes ou desassemblagem. A imagem original fica onde está; arquivos de extração são criados num diretório temporário do sistema e removidos ao terminar.

### Antes de executar

- Mantenha a imagem fora da pasta do repositório.
- Se você tem um arquivo dividido como `.7z.001`, `.7z.002` etc., mantenha todas as partes juntas e extraia a partir da parte `.7z.001` com 7-Zip (Windows) ou `7z x "arquivo.7z.001"` (Linux). Passe ao programa o arquivo resultante `.cia`, `.cci` ou `.3ds`, não uma parte `.001`.
- Tenha uma instalação local do CTRTool. O procedimento não obtém chaves nem contorna criptografia; se o conteúdo precisar de chaves que você não possui, a ferramenta falha de forma explícita.
- A imagem precisa ser uma entrada obtida e utilizada de acordo com os direitos aplicáveis. Não a adicione ao Git nem envie os resultados privados para issues, pull requests ou artifacts.

### Comandos

No PowerShell, ajuste os caminhos para os arquivos locais:

```powershell
python tools/local_3ds_intake.py `
  --image "D:\Jogos\ultra-sun.cia" `
  --target ultra-sun `
  --format cia `
  --ncch-index 0 `
  --ctrtool "C:\Ferramentas\ctrtool.exe"
```

Se o NCCH exigir um banco de seeds, acrescente `--seeddb` apontando para um arquivo local que você já possua e esteja autorizado a usar. O PokeUltrarecomp não baixa, gera ou recupera seeds/chaves. Mantenha esse arquivo fora do repositório; a ferramenta não imprime o caminho no JSON nem envia o arquivo.

No Linux:

```bash
python3 tools/local_3ds_intake.py \
  --image "$HOME/Jogos/ultra-sun.cci" \
  --target ultra-sun \
  --format cci \
  --ncch-index 0 \
  --ctrtool "$HOME/bin/ctrtool"
```

No Linux, adicione `--seeddb "$HOME/dados-locais/seeddb.bin"` quando necessário. Use apenas um banco existente e autorizado. Não o coloque no Git nem o envie para issues, secrets do Actions ou artifacts.

Ultra Moon deve ser selecionado separadamente com `--target ultra-moon`. `--format` precisa corresponder à imagem real (`3ds`, `cci` ou `cia`). Para incluir o censo agregado do Ghidra, acrescente `--ghidra-headless` com o caminho para o executável local `analyzeHeadless`; essa etapa é opcional.

A saída é JSON com contagens agregadas e campos explícitos de que a imagem não foi enviada. Ela não inclui caminho local, bytes, hash, endereço de função, palavras de instrução ou desassemblagem. A ferramenta também marca explicitamente que equivalência semântica ainda não foi verificada e que o jogo não foi iniciado.

Validação de segurança com fixtures sintéticas, sem imagem de jogo:

```bash
python -m unittest discover -s tests -p 'test_local_3ds_intake.py' -v
```

Essa suíte testa o contrato local e o relato seguro; não substitui a execução local do intake numa imagem real nem valida uma função real recompilada.

## Privacidade e limitações

A imagem completa trafega do seu provedor para a infraestrutura de GitHub Actions. Ela não passa pelo anexo do ChatGPT e não é guardada como artifact do workflow, mas o processamento acontece em uma máquina de nuvem de terceiros. Use esse método somente se estiver confortável com isso e com as condições do seu provedor de armazenamento.

O job não publica bytes do jogo, relatórios de desassembly, nomes de função, endereços de candidatos ou arquivos derivados como artifacts. Para NCSD, ele lê somente o pequeno cabeçalho e compara o Program ID do NCCH selecionado ao perfil; essa comparação não autentica a imagem nem a revisão exata. As contagens de prólogos e retornos são heurísticas: padrões podem ocorrer em dados, e uma sequência linear pode atravessar dados ou ignorar desvios. A etapa opcional Ghidra usa a análise automática do ELF privado e publica somente contagens agregadas de funções detectadas, faixas de tamanho, indicadores de retorno e frequências de mnemônicos em corpos curtos sem chamadas. As fronteiras de função e o estado ARM/Thumb não são considerados validados; a ausência de símbolos e de prova independente continua sendo uma limitação. O job ainda não recompila uma função, não inicia o jogo e não produz um porte jogável. O próximo estágio exige confirmar manualmente uma função selecionada, analisar seus limites/efeitos e testar uma tradução nativa sem registrar desassemblagem em logs públicos.

Se você não quiser enviar a ROM a nenhum serviço de nuvem, a alternativa é processamento local. Não há como analisar bytes que não estejam disponíveis nem localmente nem em algum armazenamento acessível ao ambiente de análise.
