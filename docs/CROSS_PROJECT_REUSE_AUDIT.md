# Auditoria de reutilização cruzada — PokeUltrarecomp × New Horizons Recomp

**Data:** 25 de outubro de 2026  
**PokeUltrarecomp/main:** 76e622dacfa3e0269a57f93607ce15dd6ea4dd69  
**New_horizons_recomp/main:** dcb5404386ef014335e69a2ddb181e7eae5d824b

Esta avaliação compara arquitetura, ferramentas, testes e estado de validação. Nenhum código-fonte foi copiado entre os projetos nesta auditoria.

## Veredito executivo

- **New Horizons Recomp (NHC)** tem bases C++ de recompilação estática, IR/lowering/codegen, runtimes GBA e NDS ARM9/ARM7, além de host SDL/Vulkan, input e áudio.
- **PokeUltrarecomp** tem ferramentas direcionadas ao executável 3DS: intake ExHeader/ExeFS .code, inspeção de intervalos ARM/Thumb, CFG e efeitos conservadores, contratos de função e relatório de cobertura por classes de opcode.
- A CI mais recente observada para a main do NHC reportou falha nos quatro jobs e a implantação de Pages também falhou. O motivo específico não foi confirmado nesta auditoria; não devemos presumir a causa.
- A execução mais recente observada do Poke passou em **318 testes**, com matriz diferencial **96/96** e verificador de segurança aprovado: [workflow 40217083770](https://github.com/CarlosCosta07-s/PokeUltrarecomp/actions/runs/40217083770).

A troca mais útil no curto prazo é compartilhar contratos, formatos de relatórios e vetores sintéticos; código de runtime deve esperar pela validação do NHC, uma comparação de ISA/ABI e revisão da procedência por arquivo.

## 1. O que o New Horizons pode oferecer ao PokeUltrarecomp

| Componente do NHC | Valor potencial | Limite da transferência |
| --- | --- | --- |
| Pipeline NDS em nds/recompiler: decoder, CFG, IR, lowering, codegen C++ e recompilation pipeline | Referência arquitetural para evoluir da POC sintética a uma pipeline explícita decode → CFG → IR → código host | NDS ARM9/ARM7 não é ARM11/3DS. Instruções, CPU, exceções, memória, módulos e serviços exigem adaptação e validação próprias. |
| Modelo tipado de instrução ARM, fluxo, operandos e masks de registradores/flags | Inspiração para substituir gradualmente tuplas de inspeção por estruturas tipadas e relatórios explícitos | O decoder NDS não deve ser tratado como decoder ARMv6K do 3DS; instruções semânticas não verificadas continuam desconhecidas. |
| CFG/IR/codegen GBA e registry de blocos compilados | Referência para identidade de bloco por endereço/estado ISA, despacho, resultados de erro e limites de execução | GBA usa ARM7TDMI/ARMv4T. Memória, IRQ, BIOS/HLE e dispositivos GBA não são serviços do 3DS. |
| Host platform: janela SDL/Vulkan, input, mixer PCM, saída SDL2 e fila SPSC | Possíveis interfaces genéricas de host PC para o futuro runtime 3DS | Não fornece automaticamente renderer PICA200, DSP, temporização nem serviços Horizon. |
| Perfis do launcher, readiness gates, CMake/CTest e CI | Padrões para evitar promover um título detectado ou função compilada a jogo validado | O Poke precisa manter status próprios de análise, recompilação e execução; não tornar Ultra Sun/Moon lançável por mera identificação. |

Referências: [decoder ARM NDS](https://github.com/CarlosCosta07-s/New_horizons_recomp/blob/dcb5404386ef014335e69a2ddb181e7eae5d824b/nds/recompiler/src/arm_decoder.cpp), [IR lowering NDS](https://github.com/CarlosCosta07-s/New_horizons_recomp/blob/dcb5404386ef014335e69a2ddb181e7eae5d824b/nds/recompiler/src/ir_lowering.cpp), [pipeline NDS](https://github.com/CarlosCosta07-s/New_horizons_recomp/blob/dcb5404386ef014335e69a2ddb181e7eae5d824b/nds/recompiler/src/recompilation_pipeline.cpp), [registry de blocos GBA](https://github.com/CarlosCosta07-s/New_horizons_recomp/blob/dcb5404386ef014335e69a2ddb181e7eae5d824b/gba/recompiler/include/esmerald/gba_compiled_block_registry.h) e [host platform](https://github.com/CarlosCosta07-s/New_horizons_recomp/tree/dcb5404386ef014335e69a2ddb181e7eae5d824b/platform).

## 2. O que o PokeUltrarecomp pode oferecer ao New Horizons

| Componente do Poke | Valor potencial para NHC | Limite da transferência |
| --- | --- | --- |
| Intake 3DS: ExHeader/ACI, segmentos, tamanhos, identidade e hashes locais | Padrão de relatório local, fail-closed em identidade conflitante e ausência de bytes do jogo no Git/CI | Parser específico de ExHeader/ExeFS; não substitui o parser NDS nem o preflight de ROM GBA. |
| Inspetor de intervalo: endereço, estado ISA e contagem explícitos | Melhorar a evidência de uma região selecionada sem inventar limites de função; deixar desconhecidos/encodings não suportados visíveis | É um inspetor 3DS de subconjunto, não um compilador e não substitui a CFG/IR C++ do NHC. |
| CFG e efeitos conservadores ARM/Thumb | Formato de blocos candidatos, fluxo indireto e efeitos de registradores/flags/memória com incerteza explícita | Não prova alcançabilidade nem ABI real; adaptar às instruções e ao modelo de CPU do backend destino. |
| Contrato de função declarativo | Estruturar entradas/saídas, clobbers/preservados, flags, stack delta, memória, chamadas, retorno e oráculo independente | A implementação atual admite apenas Ultra Sun/Moon e a ferramenta não está pronta para GBA/NDS. |
| Resumo agregado de cobertura | Resumo de classes de opcode sem expor endereços individuais, palavras de instrução ou bytes | Janelas selecionadas não equivalem a cobertura integral do jogo; entradas e relatórios derivados de ROM devem permanecer locais. |
| POCs e fixtures sintéticas ARM/Thumb | Base para criar vetores sintéticos de conformidade independentes por ISA e validar flags, branches, budgets e recusas | O Poke não é automaticamente o oráculo do NHC nem o inverso; cada backend precisa validar a versão de ISA aplicável. |

Referências: [intake 3DS](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/inspect_3ds_target.py), [inspetor de intervalos](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/inspect_3ds_code_range.py), [CFG](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/arm_thumb_cfg.py), [efeitos](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/arm_thumb_effects.py), [contrato de função](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/check_function_contract.py) e [resumo de cobertura](https://github.com/CarlosCosta07-s/PokeUltrarecomp/blob/76e622dacfa3e0269a57f93607ce15dd6ea4dd69/tools/summarize_code_coverage.py).

## 3. Decisões de reutilização

- **Compartilhar primeiro:** formatos de relatórios, schema de contratos, critérios success/failure/inconclusive/not-run e fixtures sintéticas baseadas em especificações públicas.
- **Adaptar depois:** relatórios de efeitos/CFG/cobertura do Poke para complementar a análise NDS/GBA; modelos de IR, codegen e despacho do NHC como referência para uma futura pipeline do Poke.
- **Não copiar diretamente:** runtime, BIOS/HLE, memória, timing, GPU, áudio, manifests de assets ou lógica específica de GBA/NDS; tampouco assumir que o decoder NDS já é compatível com ARM11/3DS.
- **Não promover para lançamento:** perfil detectado, intervalo inspecionado ou função compilada não comprovam que o jogo inicia ou pode ser jogado.
- **Prioridade zero:** entender e corrigir as falhas da CI atual do NHC antes de depender de sua integração de build.

## 4. Licença e procedência

Os textos de licença vistos nas raízes indicam GPL-3.0 no Poke e AGPL-3.0 no NHC. A FSF documenta que módulos GPLv3 e AGPLv3 podem ser combinados, cumprindo-se os termos aplicáveis: [FAQ oficial sobre AGPLv3/GPLv3](https://www.gnu.org/licenses/gpl-faq.en.html#AGPLGPL).

Isso não aprova automaticamente a cópia de um arquivo específico. O NHC registra como pendente a confirmação do escopo da licença raiz e tem submódulos com licenças próprias; o Poke também registra dúvidas de procedência/abrangência de seu LICENSE. A procedência precisa ser revisada por arquivo, incluindo autores, revisão, licença e avisos. Código e índices associados a Pokémon Emerald ou outro jogo não devem ser tratados como lógica genérica transferível.

**Nenhuma implementação foi copiada entre os repositórios nesta auditoria.**

## 5. Sequência recomendada

1. Reproduzir as falhas da CI do NHC e deixar sua main verde.
2. Especificar um pequeno formato compartilhado de vetores sintéticos ARM/Thumb com ISA explícita e resultados esperados independentes; manter as implementações de cada projeto separadas.
3. Adaptar o formato de contratos/cobertura do Poke para complementar auditorias NDS/GBA, sem publicar dumps, bytes ou relatórios sensíveis.
4. Evoluir o Poke com IR tipado e etapas decode → CFG → IR → codegen inspiradas na arquitetura do NHC, mas validando cada instrução ARMv6K por conta própria.
5. Avaliar componentes host genéricos do NHC somente após revisão de licenças e só quando houver mapeamento dos serviços 3DS.

Meta: reduzir duplicação de validação e ganhar velocidade sem acoplar CPU, runtime ou dados de consoles diferentes.
