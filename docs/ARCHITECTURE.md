# Arquitetura proposta

**Status:** proposta conceitual. Nenhum componente descrito neste documento é declarado implementado.

## Princípios

- Separar lógica do jogo reconstruída de serviços de plataforma.
- Desenvolver e testar uma interface host por vez, com casos sintéticos e resultados observáveis.
- Tratar código recompilado, código semanticamente reconstruído e componentes de compatibilidade como categorias distintas.
- Não adicionar placeholders ou stubs fictícios só para preencher diretórios.
- Manter recursos do jogo, entradas locais, dados privados e artefatos gerados fora do Git.
- Escolher APIs de plataforma e gráficos somente após uma prova isolada, documentada e licenciada.

## Visão em camadas

~~~text
Entradas locais autorizadas e configuração
                  |
                  v
        Loader / identidade do alvo
                  |
                  v
    Módulos e lógica reconstruída do jogo
                  |
                  v
     Contratos/ABI e estado de execução
                  |
                  v
       Camada de abstração de plataforma
       |          |          |          |
       v          v          v          v
   Gráficos     Áudio     Entrada     Arquivos/
   e janela                teclado     salvamento
       |          |          |          |
       +----------+----------+----------+
                  |
                  v
       Serviços Windows e APIs host

Serviços transversais: memória, temporizadores, sincronização,
módulos dinâmicos, logging, telemetria local e testes.
~~~

## Componentes propostos

### 1. Código recompilado ou reconstruído

Código convertido a partir de instruções ARM/Thumb, funções reconstruídas manualmente ou lógica reescrita precisam registrar origem, endereço/identidade de referência, commit da ferramenta, método de construção, status de correspondência e testes. Uma compilação bem-sucedida só demonstra compilação. A equivalência precisa ser demonstrada separadamente por verificação diferencial ou comportamento de referência.

O código recompilado pode depender de convenções, estado de CPU, endereçamento, exceções, callbacks e dados específicos de 3DS. Não deve ser tratado como C/C++ portátil apenas porque o recompilador gerou código C.

### 2. ABI, memória e estado da CPU

Definir contratos explícitos para largura e alinhamento de tipos, registradores/flags ainda referenciados, endianness, limites de memória, callbacks e propagação de erros. Registrar se cada rotina depende de endereço fixo, relocação, módulo dinâmico ou estado global. Evitar fingir que um endereço ou layout foi conhecido quando não há evidência.

### 3. Camada de abstração de plataforma

Interfaces propostas:
- filesystem e diretórios de usuário;
- salvamento, gravação atômica, backup e recuperação;
- relógio, temporizadores, espera e limites de frame;
- threads, mutexes, eventos, sincronização e ordenação;
- entrada, foco da janela e dispositivos removíveis;
- áudio e ciclo de vida do dispositivo;
- janela, superfícies de apresentação e diagnóstico de GPU;
- carregamento de módulos, símbolos, dependências e registros;
- serviços específicos do 3DS ainda exigidos por caminhos de jogo.

A camada deve declarar quais comportamentos são reproduzidos, aproximados ou ainda não suportados. Não implementar interfaces sem evidência de que o alvo selecionado precisa delas.

### 4. Renderização para PC

Investigar primeiro um teste host sem conteúdo proprietário. Comparar opções compatíveis com Windows, por exemplo SDL2 para janela/entrada e uma API gráfica separada (OpenGL, Vulkan ou Direct3D), sem escolher uma definitivamente nesta fase. Uma API gráfica moderna não substitui automaticamente o comportamento do GPU do 3DS: registradores, comandos, shaders, render targets, depth/stencil, texturas, formatos, sincronização e temporização devem ser mapeados e testados.

### 5. Áudio

Separar geração/mixagem do áudio da saída do dispositivo. Definir taxa de amostragem, canais, formato, latência, buffers, pausa, foco, perda de dispositivo e política de encerramento. Testes devem usar tons ou buffers sintéticos.

### 6. Entrada de teclado e controle

Traduzir teclado, teclado numérico quando aplicável, controle e touch/mouse para eventos internos. Definir repetição, zonas mortas, foco, remapeamento, estados analógicos e ordem de eventos. Testar desconexão/reconexão sem depender de jogo real.

### 7. Sistema de arquivos e salvamento

Separar recursos somente de leitura, estado persistente e arquivos temporários. Não buscar arquivos em locais arbitrários nem sobrescrever dados externos. Definir formato, versão, verificação de integridade, escrita atômica, backup e tratamento de salvamento corrompido. A origem de todos os recursos deve ser permitida e documentada; conteúdo proprietário não é incluído nos commits ou artefatos distribuídos.

### 8. Temporizadores, memória e sincronização

Especificar relógio monotônico, temporização de jogo e espera de serviço. Projetar limites para alocação e acesso à memória, alinhamento e vida útil de buffers. Testar concorrência, deadlocks, corrida, shutdown e recuperação. Não assumir que executar mais rápido ou no mesmo FPS significa equivalência temporal.

### 9. Bibliotecas dinâmicas e módulos

Criar um inventário de módulos e suas dependências; separar módulos estáticos de dinâmicos. Registrar carregamento, relocação, resolução de imports/exports, inicializadores, descarregamento e ciclo de vida. O contrato de um módulo deve ser testável sem empacotar arquivos do jogo.

### 10. Testes e diagnóstico

Camadas de teste propostas:
- testes unitários sintéticos;
- testes de ABI e memória;
- verificação diferencial de funções reconstruídas;
- testes host de gráficos, áudio, input, arquivos e sincronização;
- testes de integração do runtime com módulos autorizados;
- testes de regressão e estabilidade;
- testes de jogo local apenas em ambiente do mantenedor, sem entradas nem logs proprietários publicados.

Os logs devem omitir caminhos de usuário, hashes de dumps privados, chaves, tokens, nomes de conta e conteúdo extraído. Relatórios compartilhados devem ser redigidos.

## Decisões ainda abertas

- Como gerar/organizar código reconstruído sem incorporar conteúdo de origem não licenciado.
- Se o runtime usará código recompilado de 3dsrecomp, reconstrução própria ou abordagem mista.
- Quais serviços mínimos substituir primeiro.
- API gráfica final e bibliotecas de áudio/entrada.
- ABI dos módulos, estratégia para CRO e loader.
- Alvos mínimos de Windows, arquitetura CPU e estratégia de distribuição.

Cada decisão deve citar evidência, impacto sobre licença, custo de manutenção e critério de teste antes de ser fixada.
