# Legal e propriedade intelectual

Este documento apresenta precauções de engenharia e publicação. **Não é aconselhamento jurídico e não garante que qualquer atividade seja legal.** A legislação aplicável depende dos fatos, das jurisdições e das medidas técnicas envolvidas. Em caso de dúvida relevante, interrompa a atividade afetada e consulte um profissional qualificado.

## Aviso de independência obrigatório

> PokeUltrarecomp é um projeto independente de pesquisa e fãs. Não é afiliado, patrocinado, autorizado ou endossado pela Nintendo, GAME FREAK, Creatures Inc. ou The Pokémon Company. Pokémon, os títulos dos jogos, personagens e demais propriedades relacionadas pertencem aos respectivos titulares.

O aviso descreve a independência pretendida. Não é autorização dos titulares, não concede licença e não constitui imunidade contra reclamações.

## Conteúdo proibido no repositório e na distribuição

Não adicionar a commits, issues, pull requests, Releases, Pages, pacotes, anexos ou artefatos de CI:

- ROMs, dumps, arquivos CIA/CXI/CCI, atualizações ou outras imagens/cópias dos jogos;
- firmware, chaves, certificados ou dados destinados a desbloquear/acessar conteúdo protegido;
- executáveis proprietários dos jogos ou seus componentes extraídos;
- texturas, modelos, mapas, músicas, sons, imagens, fontes, vídeos ou outros recursos protegidos extraídos dos jogos;
- conteúdo privado de logs, configurações, perfis ou ferramentas que exponha dados sensíveis;
- binários gerados a partir de inputs proprietários quando não houver verificação dos direitos necessários para a redistribuição.

Não orientar ou facilitar a obtenção de cópias não autorizadas. Entradas locais para pesquisa devem ficar fora do Git e de serviços de CI, com exclusões verificadas antes dos commits. Regras de ignore não removem arquivos que já estão sendo rastreados.

## Descompilação, extração e proteções técnicas

- Não presumir que possuir uma cópia legítima torna automaticamente lícitas a extração, a modificação, a recompilação ou a remoção/contorno de proteções tecnológicas.
- Não presumir que objetivo educacional, gratuidade ou ausência de finalidade comercial tornam automaticamente lícita toda atividade.
- Avaliar separadamente direitos autorais, contratos aplicáveis, marcas, leis locais e regras sobre medidas tecnológicas de proteção.
- Não publicar executáveis que incorporem código ou recursos proprietários sem confirmar os direitos necessários para uso e redistribuição.
- Se uma tarefa depender de contorno de proteção, distribuição de conteúdo protegido ou uma interpretação legal duvidosa, suspenda a tarefa e procure orientação jurídica profissional antes de prosseguir.

## Licenças de código e dependências

- Verificar a licença de cada arquivo/fonte e dependência antes de reutilizar código.
- Não inferir licença pelo fato de um repositório ser público, por um campo de metadados isolado ou por o projeto aceitar issues/PRs.
- Registrar URL de origem, commit completo, licença aplicável, copyright, atribuições exigidas, alterações feitas e dependências transitivas em [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
- Preservar avisos de copyright e textos de licença quando exigidos.
- Separar a licença de uma ferramenta da licença do código que ela gera e dos direitos sobre os dados do jogo.
- Não copiar repositórios inteiros nem vendorizá-los antes da análise de procedência, licença e necessidade técnica.
- Não adicionar uma nova licença geral até que a procedência de todo o conteúdo existente esteja verificada e o mantenedor confirme quais direitos pode conceder.

## Atenção para o LICENSE já existente

O repositório continha um arquivo LICENSE com o texto padrão da GNU GPL versão 3 no commit inicial. Não há documentação no repositório que identifique o autor, a data/intenções de concessão ou o conteúdo abrangido por essa licença. Este trabalho não substituiu nem removeu o arquivo. O mantenedor deve decidir, com base na procedência do conteúdo existente e orientação qualificada quando necessário, se o arquivo reflete sua intenção e quais arquivos podem estar cobertos. Até essa revisão, não assuma que o arquivo autoriza licenciar material de terceiros ou conteúdo proprietário.

## Publicação e resposta a incidentes

- Nunca enviar chaves, senhas, tokens, cookies, dumps ou caminhos locais sensíveis.
- Não usar GitHub Actions para baixar ou processar jogos, firmware, chaves ou recursos proprietários.
- Verificar diffs e artefatos gerados antes de publicar; excluir dados de jogo e metadados privados.
- Em uma alegação plausível de violação, pause a distribuição do material afetado, preserve registros relevantes sem republicar o conteúdo e procure orientação jurídica. Não responda com garantias legais nem com afirmações especulativas.
- Correções técnicas e remoções de conteúdo devem ser feitas conforme a orientação profissional e as políticas da plataforma.

## Referências oficiais consultadas

- [Política de propriedade intelectual da Nintendo (PT-BR)](https://pt-americas-support.nintendo.com/app/answers/detail/a_id/50036/p/171)
- [Guia do GitHub para notificações de remoção DMCA](https://docs.github.com/en/site-policy/content-removal-policies/guide-to-submitting-a-dmca-takedown-notice)
- [Documentação do GitHub sobre licenciamento de repositórios (PT)](https://docs.github.com/pt/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)

Os links foram verificados na auditoria documental em 24 de outubro de 2026. Revise-os periodicamente, pois páginas e políticas podem mudar.
