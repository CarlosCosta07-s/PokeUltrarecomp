# Pesquisa de bases de código ARM e recompilação

**Data da consulta:** 2026-10-24  
**Objetivo:** estudar fontes públicas de código relacionadas a decodificação ARM, emulação, recompilação estática/dinâmica e validação diferencial, para orientar o POC-001.  
**Resultado de reutilização:** esta é uma auditoria de referência, não uma incorporação. Nenhum código dos projetos abaixo foi copiado para PokeUltrarecomp.

## Fontes de código consultadas

### 1. 3dsrecomp — recompilador estático para Nintendo 3DS

- **Código:** [repositório](https://github.com/fearkov/3dsrecomp)
- **Observação técnica:** identifica funções ARM/Thumb/VFP e gera C; instruções não suportadas podem continuar no interpretador de Zakuro. A documentação descreve testes diferenciais por função, comparando registradores, flags e memória entre o código recompilado e o interpretador.
- **Aplicação ao projeto:** referência mais próxima do alvo do PokeUltrarecomp; útil como modelo para delimitação de instruções e validação diferencial.
- **Licença:** não foi encontrado um arquivo `LICENSE` na raiz da revisão inspecionada. A procedência/licença deve ser confirmada com os mantenedores antes de qualquer reutilização. **Não copiar código neste momento.**

### 2. GBARecomp (mstan) — recompilador estático ARM7TDMI

- **Código:** [repositório](https://github.com/mstan/gbarecomp), [arquitetura](https://github.com/mstan/gbarecomp/blob/main/docs/ARCHITECTURE.md) e [princípios](https://github.com/mstan/gbarecomp/blob/main/PRINCIPLES.md)
- **Observação técnica:** organiza decodificador, IR, analisador, interpretador, gerador C++, runtime e testes em camadas. Os princípios salientam que flags de condição, estado do PC, interworking ARM/Thumb e exceções precisam de semântica explícita.
- **Aplicação ao projeto:** excelente referência arquitetural para além da tradução de uma sequência linear de instruções.
- **Licença:** o arquivo `LICENSE` consultado contém **PolyForm Noncommercial 1.0.0**. Não assumir compatibilidade com uso comercial ou distribuição futura; nenhuma parte do código foi copiada.

### 3. Dynarmic — recompilador dinâmico ARM

- **Código:** [repositório](https://github.com/lioncash/dynarmic) e [documento de arquitetura](https://github.com/lioncash/dynarmic/blob/master/docs/Design.md)
- **Observação técnica:** descreve o pipeline decodificação → tradução para IR → otimização → emissão de código de máquina do host → execução. Suporta frontends A32/A64.
- **Aplicação ao projeto:** sugere que o POC eventualmente deve separar decodificação, representação intermediária e emissão, em vez de misturar todas as regras num único gerador.
- **Licença:** o `LICENSE.txt` consultado contém uma concessão permissiva de uso/cópia/modificação/distribuição. Confirmar o texto completo, o commit e avisos de dependências antes de eventual incorporação; não copiamos código.

### 4. Unicorn Engine — framework de emulação de CPU

- **Código:** [repositório e README](https://github.com/unicorn-engine/unicorn)
- **Observação técnica:** framework multiplaforma e multi-arquitetura baseado no QEMU, com suporte a ARM e ARM64. É um motor de execução/emulação, não um recompilador estático ARM→C.
- **Aplicação ao projeto:** pode ser avaliado no futuro como oráculo de execução para fixtures sintéticas ou testes diferenciais, com versão fixada e estado inicial explícito.
- **Licença:** o README consultado declara **GPLv2**. Não integrar como dependência nem copiar código sem uma revisão específica de compatibilidade e distribuição.

### 5. Capstone — disassembler

- **Código:** [repositório e README](https://github.com/capstone-engine/capstone)
- **Observação técnica:** decodifica instruções de várias arquiteturas e pode expor registradores implícitos lidos/escritos; não executa instruções nem confirma, sozinho, a semântica da CPU.
- **Aplicação ao projeto:** uma futura integração de teste pode comparar a classificação de instruções do decodificador próprio com a classificação de Capstone, sem tratar isso como prova de equivalência.
- **Licença:** o README consultado declara licença BSD. Qualquer dependência ainda exigiria fixar a versão e revisar avisos e build.

### 6. MAME — núcleo emulador ARM7

- **Código:** [implementação ARM7](https://github.com/mamedev/mame/blob/master/src/devices/cpu/arm7/arm7.cpp), [cabeçalho do núcleo](https://github.com/mamedev/mame/blob/master/src/devices/cpu/arm7/arm7core.h) e [licenciamento](https://github.com/mamedev/mame#license)
- **Observação técnica:** oferece uma implementação C++ de um núcleo ARM de 32 bits com execução real de instruções. É útil como fonte de perguntas de teste para semântica de CPU, não como prova automática de correção do POC.
- **Licença:** o projeto MAME declara uma distribuição global GPL-2.0-or-later com muitos arquivos sob BSD-3-Clause; o cabeçalho de arquivo específico deve ser conferido. Isso exige auditoria por arquivo antes de reutilização.

### 7. Linux — tabelas de decodificação ARM

- **Código:** [arch/arm/probes/decode-arm.c](https://github.com/torvalds/linux/blob/master/arch/arm/probes/decode-arm.c) e [regras de licenciamento](https://github.com/torvalds/linux/blob/master/Documentation/process/license-rules.rst)
- **Observação técnica:** contém tabelas de máscaras e valores para classificar encodings ARM; entre outros, rotula padrões de instruções de processamento de dados como BIC, MVN e CMN. É um decodificador para a infraestrutura de probes do kernel, não um recompiler completo.
- **Aplicação ao projeto:** útil para comparar padrões de bits e projetar casos negativos de decodificação.
- **Licença:** o kernel declara GPL-2.0-only com uma exceção específica de syscall; verificações de licença por arquivo continuam necessárias. Nenhum código foi copiado.

### 8. Zakuro — emulador/runtime Nintendo 3DS

- **Código:** [repositório](https://github.com/fearkov/zakuro), [compatibilidade publicada](https://github.com/fearkov/zakuro/blob/main/COMPATIBILITY.md) e [licença](https://github.com/fearkov/zakuro/blob/main/LICENSE)
- **Observação técnica:** serve como referência de execução/interpretação para caminhos ainda não recompilados; a documentação de compatibilidade separa jogos que iniciam, chegam a menus ou são jogáveis.
- **Aplicação ao projeto:** reforça a importância de registrar com precisão quais caminhos foram executados e de não confundir “compilou” com “jogo funciona”.
- **Licença:** o arquivo `LICENSE` consultado declara MIT. Isso não é autorização para reutilizar código de outro projeto (incluindo 3dsrecomp), nem substitui revisão de dependências e avisos.

### 9. GBARecomp (sp00nznet) — implementação estática alternativa

- **Código:** [repositório](https://github.com/sp00nznet/gbarecomp)
- **Observação técnica:** uma outra implementação experimental que traduz ARM/Thumb para C e associa o código gerado a um runtime GBA. Serve como comparação de organização de CLI, projeto gerado e testes de conformidade.
- **Licença:** o arquivo `LICENSE` consultado declara MIT. A implementação e seu estado devem ser avaliados separadamente da versão `mstan/gbarecomp); os dois projetos não devem ser tratados como o mesmo código-base.

## Referência arquitetural usada para conferir a semântica

A [Arm Instruction Set Reference Guide](https://documentation-service.arm.com/static/6245c734b059dc5ff9a8bdab) confirma a família de instruções de processamento de dados e o papel dos flags. A documentação de ARM distingue instruções que escrevem um resultado em registrador de instruções de comparação/teste que atualizam flags sem gravar o resultado.

**Implicação para o POC-001:** `CMN` não deve ser implementado como uma soma comum. Ele atualiza N, Z, C e V e descarta o resultado; POC-001 ainda não modela CPSR/NZCV, então CMN deve esperar até que estado de flags e testes correspondentes estejam especificados. A extensão mais segura nesta etapa é `MVN` imediato sem atualização de flags, mantendo o escopo restrito.

## Conclusões práticas

1. Manter o decodificador conservador: recusar instruções, registradores e campos que não foram implementados explicitamente.
2. Separar gradualmente decodificação, representação intermediária e emissão; manter cada expansão pequena e coberta por testes positivos e negativos.
3. Construir testes diferenciais sintéticos antes de usar código de jogo; quando um oráculo de execução for escolhido, comparar os estados relevantes, incluindo registradores e flags.
4. Não importar código, dependências ou fragmentos de nenhuma dessas fontes antes de registrar commit exato, licença por arquivo, dependências, avisos e compatibilidade com o escopo de distribuição.
5. Não usar código gerado a partir de ROMs ou ativos de jogos em testes públicos, commits ou releases.

## Limites da pesquisa

Consulta documental de repositórios públicos e arquivos de licença na data acima. Não foi feito clone/build integral desses projetos, não se verificou a execução de seus testes, e a análise não é aconselhamento jurídico nem uma auditoria completa de suas dependências. Nenhuma ROM, dump, firmware, chave ou recurso de jogo foi usado.
