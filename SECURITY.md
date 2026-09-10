# Security policy

## Supported versions

Forge is currently an **alpha reference implementation**. Only the latest
commit on the default branch receives security fixes.

## Reporting a vulnerability

Do not open a public issue for suspected command-execution, approval-bypass,
credential-leakage, or path-traversal vulnerabilities. Use the repository
host's private security-advisory feature and include reproduction steps,
affected versions, and potential impact.

## Execution boundary

The built-in `Sandbox` is a restricted local subprocess runner, not an OS-level
sandbox. It disables shell evaluation, uses an executable allowlist, limits
runtime, minimizes the environment, and fixes the working directory. Untrusted
generated code can still consume local resources or exploit an allowed runtime.
Production deployments must execute it inside a disposable container or microVM
with resource quotas, no host mounts, and network access denied by default.

External commands configured with `--provider-command` are trusted integration
processes, not sandboxed model output. They receive a minimal environment and
only explicitly forwarded variables, but retain the operating-system permissions
of the Forge process. Keep provider implementations outside untrusted
repositories and isolate them as a separate service in production.
