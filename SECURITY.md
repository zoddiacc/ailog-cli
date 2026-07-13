# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Instead, report privately via GitHub's
[private vulnerability reporting](https://github.com/zoddiacc/ailog-cli/security/advisories/new)
(Security → Report a vulnerability). If that is unavailable, email
**sanjayjithm@gmail.com** with details and steps to reproduce.

We aim to acknowledge reports within a few days and will keep you updated on a fix.

## Supported versions

Security fixes target the latest released version on PyPI (`ailog-cli`). Please
upgrade to the latest version before reporting: `pip install --upgrade ailog-cli`.

## Security model (what to keep in mind)

AILog is a local CLI, but it processes untrusted input and can talk to remote
services, so a few things are worth knowing:

- **Log content is untrusted.** Any app on a connected device can emit arbitrary
  logcat lines. AILog sanitizes terminal control sequences before printing and
  HTML-escapes report output, but report responsibly if you find a gap.
- **Cloud providers receive log content.** With a cloud provider (OpenAI/Anthropic),
  log excerpts and, for crash fixes, source snippets are sent to that provider.
  Secret redaction is **on by default for cloud providers**. The default provider
  is local Ollama, where nothing leaves your machine.
- **API keys** are stored in `~/.config/ailog/config.json` with `0600` permissions;
  environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) take precedence.

Thank you for helping keep AILog and its users safe.
