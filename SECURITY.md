# Política de segurança

## Dados sensíveis

- **Nunca** commite ficheiros `.env`, tokens Twilio, PATs do GitHub ou chaves de API.
- Os tokens Twilio devem existir apenas em **GitHub Actions Secrets** (CI) ou variáveis de ambiente locais (desenvolvimento).

## `repository_dispatch` (scheduler externo)

Se o repositório for **público**, recomenda-se fortemente:

1. Criar o secret `EXTERNAL_DISPATCH_TOKEN` no GitHub (valor aleatório longo).
2. Enviar o mesmo valor em `client_payload.token` em cada `POST /dispatches`.
3. O workflow `delivery-only.yml` ignora `repository_dispatch` sem token válido quando o secret está definido.

Se `EXTERNAL_DISPATCH_TOKEN` **não** estiver definido, o comportamento permanece compatível com dispatches antigos (sem `client_payload`), com menor proteção.

## Reportar vulnerabilidade

Abra um issue privado ou contacte o mantenedor do repositório com detalhes para reprodução e impacto. Não publique credenciais em issues públicos.

## Rotação de credenciais

Em caso de exposição acidental (log, screenshot, commit):

1. Rode tokens Twilio na consola Twilio.
2. Revogue o PAT do GitHub e crie outro com âmbito mínimo (`repo`, `workflow` apenas se necessário).
3. Atualize secrets no GitHub e variáveis na máquina do scheduler.
