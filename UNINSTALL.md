# Uninstalling AILog

## Installed via pip (most users)

The PyPI package is named `ailog-cli` (not `ailog`):

```bash
pip uninstall ailog-cli
```

Then remove your configuration and saved reports if you want a clean slate:

```bash
rm -rf ~/.config/ailog          # config file with provider settings, API keys
rm -rf ~/.local/share/ailog     # HTML session reports (and source, if installed via install.sh)
```

## Installed via install.sh (from source)

```bash
# Remove the launcher script
rm -f ~/.local/bin/ailog

# Remove copied source files and reports
rm -rf ~/.local/share/ailog

# Remove configuration and API keys
rm -rf ~/.config/ailog
```

If you cloned the repo, delete the `AILog/` directory as well.

## Windows

```powershell
pip uninstall ailog-cli

# Remove the launcher (if created)
Remove-Item "$env:USERPROFILE\bin\ailog.cmd" -ErrorAction SilentlyContinue

# Remove configuration
Remove-Item "$env:USERPROFILE\.config\ailog" -Recurse -ErrorAction SilentlyContinue
```

## What Gets Removed

| Path | Contents |
|------|----------|
| pip package `ailog-cli` | The `ailog` command and Python package |
| `~/.local/bin/ailog` | Launcher script (install.sh only) |
| `~/.local/share/ailog/` | HTML session reports; copied source (install.sh only) |
| `~/.config/ailog/` | Config file with provider settings, API keys |
