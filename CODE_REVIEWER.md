# Code Reviewer

Guia para revisão de código no projeto Secur. Este documento serve tanto para revisores humanos quanto para agentes automatizados de revisão.

## Objetivo

Garantir que alterações de código estejam alinhadas com o `SPEC.md` e o `README.md`, mantendo qualidade, segurança, performance e portabilidade.

## Princípios de revisão

- Verifique se a alteração atende aos requisitos do projeto.
- Prefira soluções simples e modulares.
- Mantenha o código legível e bem documentado.
- Confirme que existem testes adequados para mudanças relevantes.
- Avalie impacto em performance e recursos, especialmente para Raspberry Pi.
- Verifique dependências e compatibilidade com Linux e Raspberry Pi.

## Checklist de revisão

### Alinhamento com especificação
- A mudança está de acordo com o `SPEC.md`?
- O `README.md` ou a documentação do projeto requer atualização?
- A implementação respeita o roadmap e o escopo do MVP?

### Funcionalidade
- O código resolve o problema esperado?
- O comportamento cobre casos de uso principais e falhas esperadas?
- Há tratamento adequado de erros e falhas de entrada?

### Arquitetura e design
- O código é modular e bem separado por responsabilidades?
- Há acoplamento excessivo entre componentes?
- As abstrações fazem sentido para captura de vídeo, IA, persistência e alertas?

### Qualidade de código
- O estilo de código é consistente com Python e boas práticas.
- Há nomes claros para variáveis, funções e classes.
- O código evita duplicação desnecessária.
- Comentários e docstrings são presentes onde necessário.

### Performance e recursos
- A solução considera o uso de CPU/RAM em Linux e Raspberry Pi?
- Há otimizações razoáveis para captura de múltiplos streams e inferência de IA?
- A lógica evita loops pesados ou operações bloqueantes sem necessidade?

### Segurança e confiabilidade
- Há validação de entrada e tratamento de valores inesperados?
- O código não expõe credenciais ou dados sensíveis inadvertidamente?
- Há atenção a falhas de rede, perda de conexão e reinicializações?

### Testes e documentação
- Foram adicionados testes ou casos de validação?
- Os testes cobrem cenários relevantes e bordas?
- A documentação do novo comportamento está atualizada?

## Revisão de mudanças específicas

### Python e IA
- Verifique se dependências de ML são justificadas.
- Avalie o uso de modelos e se há fallback para ambientes sem GPU.
- Cheque se cargas de inferência são moduladas e podem ser limitadas.

### Captura de vídeo / câmeras IP
- Confirme suporte a RTSP/HTTP e reconexão automática.
- Verifique tratamento de falhas de stream e timeouts.
- Avalie se o pré-processamento de frames é eficiente.

### Dashboard e backend
- Verifique se APIs são bem definidas e documentadas.
- Confirme o uso de rotas seguras e validação de parâmetros.
- Avalie a experiência de uso na interface e histórico de eventos.

## Como usar este guia

1. Compare as alterações com o `SPEC.md` e `README.md`.
2. Aplique o checklist para cada PR ou conjunto de mudanças.
3. Faça perguntas específicas quando a implementação divergir do projeto.
4. Registre comentários claros e acionáveis para o autor.

## Exemplos de comentários de revisão

- "Essa função faz mais de uma coisa; sugiro separar captura e inferência para melhorar modularidade."
- "O tratamento de reconexão da câmera não cobre casos de desconexão prolongada."
- "Considere usar uma classe de configuração central para evitar strings duplicadas."
- "Esse módulo precisa de testes de unidade para o fluxo de eventos e alertas."
