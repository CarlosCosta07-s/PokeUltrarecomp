# Como contribuir

Obrigado pelo interesse no PokeUltrarecomp. A prioridade é produzir evidência técnica reproduzível e manter a procedência e a propriedade intelectual sob controle. O projeto ainda está em fase de pesquisa; não presuma a existência de runtime funcional.

## Antes de abrir uma issue

- Pesquise issues existentes e leia [README.md](README.md), [ROADMAP.md](docs/ROADMAP.md) e [LEGAL_AND_IP.md](docs/LEGAL_AND_IP.md).
- Use o template de tarefa de pesquisa para perguntas técnicas ou comparação de projetos.
- Defina objetivo, escopo, dependências, evidência necessária e critérios mensuráveis de aceitação.
- Indique se o trabalho requer dados de jogo, firmware, chaves, material extraído ou contorno de proteção. Se sim, pare e resolva os requisitos legais antes de prosseguir.

## Procedência e licença

Cada contribuição de código deve informar:
- autoria/procedência e origem dos trechos copiados ou adaptados;
- repositório e commit completo, quando aplicável;
- licença que autoriza a incorporação e avisos/atribuições necessários;
- dependências diretas e transitivas introduzidas;
- modificações feitas em código de terceiros;
- testes executados e como reproduzi-los.

Não copie código de repositórios que não tenham licença ou permissão clara. Não considere a visibilidade pública como autorização. Não copie repositórios de referência inteiros nem faça vendoring sem uma justificativa técnica e revisão prévia. Peça esclarecimento quando a origem de um arquivo não estiver clara.

## Conteúdo proibido

Não enviar ROMs, dumps, CIA/CXI/CCI, atualizações, firmware, chaves, executáveis proprietários ou recursos extraídos nos commits, issues, PRs, releases ou CI. Não enviar resultados gerados que contenham ou reproduzam código/recursos proprietários. Testes devem preferir fixtures sintéticas e manter qualquer entrada local fora do Git e de pipelines remotos.

Antes de cada commit, verifique `git status`, `git diff --check`, o diff completo, `git check-ignore` para entradas locais e o tamanho dos arquivos adicionados. Ignore rules não são proteção para arquivos que já estejam sendo rastreados.

Para uma verificação auxiliar sem dependências externas, execute com Python 3.10+:

    python tools/check_repository_safety.py
    python -m unittest discover -s tests -v

O verificador cobre apenas padrões conhecidos de caminhos/extensões e links Markdown relativos; ele não examina o histórico inteiro nem substitui a revisão manual.

## Pull requests

Cada PR deve conter:
- problema e objetivo delimitado;
- resumo de mudanças e o que deliberadamente não mudou;
- critério de aceitação e evidência;
- comandos e versões das ferramentas;
- resultado de testes e limitações conhecidas;
- origem/licença de componentes e atualização de THIRD_PARTY_NOTICES.md, quando necessário;
- confirmação de que nenhum conteúdo proprietário ou segredo foi adicionado.

Não declare uma função recompilada, runtime, porta nativa ou suporte a jogo como funcional sem evidência. Separar teste autorrelatado, revisão de código, compilação, teste sintético e validação de gameplay.

## Estilo

Prefira alterações pequenas, nomes explícitos, comentários para decisões não óbvias e documentação em português brasileiro. Evite dependências novas sem justificativa. Não introduza binários grandes, repositórios inteiros, cópias vendorizadas ou workflows que baixem dados proprietários. Trate todas as pessoas com respeito; consulte [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
