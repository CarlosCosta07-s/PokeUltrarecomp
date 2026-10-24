# Segurança

## Escopo

Este repositório está em fase de pesquisa. Questões de segurança podem envolver ferramentas de análise, dependências, scripts locais, salvamentos, logs, credenciais ou dados privados. Não envie conteúdo de jogo ou segredos em relatórios públicos.

## Como reportar

Para uma vulnerabilidade que possa afetar usuários, credenciais, sistemas ou a integridade de builds, **não publique detalhes exploráveis em uma issue pública**. Use o canal de contato privado de segurança disponibilizado pelo mantenedor nas configurações do repositório GitHub. Se não houver canal privado configurado, abra primeiro uma issue pública mínima pedindo contato privado, sem incluir payloads, segredos ou passos exploráveis.

Inclua versão/commit afetado, impacto esperado, ambiente, passos mínimos seguros para reproduzir e mitigação possível. Compartilhe apenas dados redigidos e artefatos não proprietários. Não incluiremos um endereço de e-mail inventado neste documento.

## Proteja credenciais e ambiente local

- Nunca solicite ou publique senha, token pessoal, chave SSH, chave API, cookie, sessão autenticada ou chave de descriptografia.
- Use gerenciadores de segredos e autenticação de menor privilégio. Não salve credenciais em scripts, .env rastreado, documentação, logs ou capturas.
- Mantenha ROMs, dumps, firmware, chaves, recursos extraídos, saves, perfis de runtime e logs privados fora do Git. Use os diretórios ignorados definidos em .gitignore e verifique se os arquivos não estão previamente rastreados.
- Não envie entradas locais a ferramentas online nem a serviços de CI.
- Redija caminhos que revelem nome de usuário, diretório pessoal, configuração privada ou identificador de arquivos locais.
- Verifique o conteúdo de arquivos antes de publicar; se um segredo foi enviado, revogue/rotacione-o imediatamente. Remover um arquivo de um commit posterior não remove o segredo do histórico.
- Baixe ferramentas e dependências de fontes oficiais, fixe versões/commits e valide hashes quando publicados pelos mantenedores.
- Não execute binários ou scripts de origem desconhecida com privilégios elevados.

## Dependências e bugs

Registre versão e commit de dependências. Reporte vulnerabilidades upstream no canal apropriado do projeto de origem; não copie código para contornar a licença. Não declare uma vulnerabilidade resolvida sem teste de regressão reproduzível.

A política deste arquivo descreve como reportar e proteger dados; não é garantia de resposta, prazo ou ausência de risco.
