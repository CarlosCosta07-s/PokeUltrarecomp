# Analisar uma imagem de Nintendo 3DS sem anexá-la ao chat

## Formatos aceitos

O workflow remoto aceita .3ds, .cci e .cia. CTRTool documenta .3ds/.cci como variantes da imagem de cartucho NCSD e .cia como arquivo de instalação. .ccd não é um formato de imagem de jogo Nintendo 3DS; confira a extensão real do arquivo se esse era o formato pretendido. Este workflow não aceita .ccd.

Referências técnicas:
- CTRTool README: https://github.com/3DSGuy/Project_CTR/blob/master/ctrtool/README.md
- CTRTool releases: https://github.com/3DSGuy/Project_CTR/releases

## Executar pelo GitHub no navegador ou celular

Este modo permite processar a imagem em um runner temporário do GitHub Actions sem executar as ferramentas no seu computador. O workflow aceita uma URL HTTPS de download direto e links de compartilhamento de arquivos do Google Drive. Para o Drive, utiliza gdown 6.4.2 para resolver as confirmações de arquivo grande e transferir a imagem; o arquivo precisa permitir acesso a quem possui o link. A URL nunca deve ser colocada no código, em uma issue ou na linha de comando de um workflow. Arquivos que exigem login, que excederam a cota de download do Drive ou que estão bloqueados pelo provedor ainda podem falhar.

1. No repositório, abra Settings, depois Secrets and variables, depois Actions. Crie o secret POKEULTRARECOMP_SOURCE_URL com a URL HTTPS de download direto. Use um link restrito/temporário se o seu provedor permitir.
2. Abra Actions, selecione Remote Nintendo 3DS container intake e toque em Run workflow.
3. Escolha ultra-sun ou ultra-moon, selecione 3ds, cci ou cia e informe o índice da partição/conteúdo (normalmente 0).
4. Consulte o resumo do job. Além da extração e da validação estrutural, ele contabiliza de forma heurística padrões comuns de prólogo ARM/Thumb dentro de `.text`. O resumo publica apenas contagens agregadas — nunca endereços candidatos, bytes ou desassemblagem. Isso não descobre nem comprova limites de função.

O workflow tem um limite de download de 8 GiB, um limite de execução de 60 minutos, usa CTRTool v1.3.0 e fixa gdown em 6.4.2 para baixar arquivos públicos do Google Drive. Se a imagem exigir chaves que o workflow não tem ou não puder ser extraída diretamente, ele falha de forma explícita; não tenta recuperar chaves ou contornar criptografia.

## Privacidade e limitações

A imagem completa trafega do seu provedor para a infraestrutura de GitHub Actions. Ela não passa pelo anexo do ChatGPT e não é guardada como artifact do workflow, mas o processamento acontece em uma máquina de nuvem de terceiros. Use esse método somente se estiver confortável com isso e com as condições do seu provedor de armazenamento.

O job não publica bytes do jogo, relatórios de desassembly ou arquivos derivados como artifacts. Ele valida o layout de segmentos e produz somente uma contagem agregada dos padrões candidatos. Padrões podem ocorrer em dados e não equivalem a funções reais. O job ainda não recompila uma função, não inicia o jogo e não produz um porte jogável. O próximo estágio exige confirmar manualmente uma função selecionada, analisar seus limites/efeitos e testar uma tradução nativa sem registrar desassemblagem em logs públicos.

Se você não quiser enviar a ROM a nenhum serviço de nuvem, a alternativa é processamento local. Não há como analisar bytes que não estejam disponíveis nem localmente nem em algum armazenamento acessível ao ambiente de análise.
