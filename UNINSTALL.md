# Uninstalling AILog

## Linux / macOS

```bash
# Remove the launcher script
rm -f ~/.local/bin/ailog

# Remove source files and examples
rm -rf ~/.local/share/ailog

# Remove configuration and API keys
rm -rf ~/.config/ailog
```

## Windows

```powershell
# Remove the launcher (if created)
Remove-Item "$env:USERPROFILE\bin\ailog.cmd" -ErrorAction SilentlyContinue

# Remove configuration
Remove-Item "$env:USERPROFILE\.config\ailog" -Recurse -ErrorAction SilentlyContinue
```

If you cloned the repo, delete the `AILog/` directory as well.

## What Gets Removed

| Path | Contents |
|------|----------|
| `~/.local/bin/ailog` | Launcher script |
| `~/.local/share/ailog/` | Source code and examples |
| `~/.config/ailog/` | Config file with provider settings, API keys |
