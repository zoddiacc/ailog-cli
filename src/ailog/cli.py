"""
CLI routing for ailog.
"""

import sys
import argparse
from .__init__ import __version__
from .build_wrapper import BuildWrapper
from .logcat_wrapper import LogcatWrapper
from .analyzer import BatchAnalyzer
from .config_manager import ConfigManager
from .display import Display


def main():
    parser = argparse.ArgumentParser(
        prog='ailog',
        description='AI-powered Android/AOSP log interpreter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  ailog build                        Run 'm' and interpret the output
  ailog build -- -j16 framework      Build with custom args
  ailog cat                          Start AI-filtered logcat
  ailog cat -s MyTag                 Filter by tag with AI interpretation
  ailog analyze build.log            Analyze a saved build log
  ailog analyze logcat.txt --full    Full analysis without noise filtering
  ailog config --show                Show current configuration
  ailog config --provider ollama     Switch to local Ollama
  ailog config --list-models         List available Ollama models
        """
    )

    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {__version__}')
    parser.add_argument('--no-color', action='store_true',
                        help='Disable colored output')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what AI call would be made without sending it')
    parser.add_argument('--show-tokens', action='store_true',
                        help='Show estimated token count for AI calls')
    parser.add_argument('--redact', action='store_true',
                        help='Strip API keys, passwords, and tokens from log content before sending to AI')

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # --- build ---
    build_parser = subparsers.add_parser('build', help='Wrap AOSP build with AI')
    build_parser.add_argument('make_args', nargs=argparse.REMAINDER,
                              help='Args to pass to make/m (after --)')
    build_parser.add_argument('--no-filter', action='store_true',
                              help='Show all logs, still add AI summary at end')
    build_parser.add_argument('--summary-only', action='store_true',
                              help='Only show AI summary, hide all raw logs')
    build_parser.add_argument('--module', type=str,
                              help='Hint the module being built for better AI context')

    # --- cat ---
    cat_parser = subparsers.add_parser('cat', help='AI-filtered adb logcat')
    cat_parser.add_argument('logcat_args', nargs=argparse.REMAINDER,
                            help='Args passed to adb logcat')
    cat_parser.add_argument('--device', '-s', type=str, metavar='SERIAL',
                            help='Target device serial (same as adb -s)')
    cat_parser.add_argument('--package', '-p', type=str, metavar='PKG',
                            help='Filter by app package name (e.g. com.example.myapp)')
    cat_parser.add_argument('--noise-level', choices=['low', 'medium', 'high'],
                            default='medium',
                            help='How aggressively to filter noise (default: medium)')
    cat_parser.add_argument('--focus', type=str,
                            help='Focus AI attention on a specific tag, PID, or keyword')
    cat_parser.add_argument('--explain', action='store_true',
                            help='Explain each error/warning inline as it appears')
    cat_parser.add_argument('--batch-interval', type=int, default=None,
                            help='Seconds between AI batch summaries (default: from config or 5)')
    cat_parser.add_argument('--no-source', action='store_true',
                            help='Skip source file reading for crash fix suggestions')

    # --- analyze ---
    analyze_parser = subparsers.add_parser('analyze', help='Batch analyze a log file')
    analyze_parser.add_argument('file', help='Log file to analyze')
    analyze_parser.add_argument('--type', choices=['build', 'logcat', 'auto'],
                                default='auto', help='Type of log file (default: auto-detect)')
    analyze_parser.add_argument('--full', action='store_true',
                                help='Disable noise filtering, analyze everything')
    analyze_parser.add_argument('--output', type=str,
                                help='Save analysis report to file')
    analyze_parser.add_argument('--focus', type=str,
                                help='Focus on a specific component or error')

    # --- config ---
    config_parser = subparsers.add_parser('config', help='Configure ailog')
    config_parser.add_argument('--show', action='store_true',
                               help='Show current configuration')
    config_parser.add_argument('--provider', choices=['ollama', 'openai', 'anthropic'],
                               help='Set AI provider')
    config_parser.add_argument('--api-key', type=str, metavar='KEY',
                               help='Set API key for current provider')
    config_parser.add_argument('--model', type=str,
                               help='Set model for current provider')
    config_parser.add_argument('--base-url', type=str,
                               help='Set custom base URL for current provider')
    config_parser.add_argument('--list-models', action='store_true',
                               help='List available models (Ollama only)')
    config_parser.add_argument('--reset', action='store_true',
                               help='Reset to defaults')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    display = Display(use_color=False if args.no_color else None)
    config = ConfigManager()
    config.dry_run = args.dry_run
    config.show_tokens = args.show_tokens
    config.redact = args.redact

    if args.command == 'config':
        handle_config(args, config, display)
    else:
        # For non-ollama providers, check API key exists
        if config.provider != 'ollama' and not config.get_api_key():
            display.error(
                f"No API key configured for {config.provider}. "
                f"Run: ailog config --api-key YOUR_KEY"
            )
            if config.provider == 'anthropic':
                display.info("Get a key at: https://console.anthropic.com")
            elif config.provider == 'openai':
                display.info("Get a key at: https://platform.openai.com/api-keys")
            display.info("Or switch to local Ollama: ailog config --provider ollama")
            sys.exit(1)

        if args.command == 'build':
            wrapper = BuildWrapper(config, display)
            wrapper.run(args)
        elif args.command == 'cat':
            wrapper = LogcatWrapper(config, display)
            wrapper.run(args)
        elif args.command == 'analyze':
            analyzer = BatchAnalyzer(config, display)
            analyzer.run(args)


def handle_config(args, config, display):
    actions_taken = False

    if args.provider:
        try:
            config.set_provider(args.provider)
            display.success(f"Provider set to: {args.provider}")
            actions_taken = True
        except ValueError as e:
            display.error(str(e))
            return

    if args.api_key:
        config.set_api_key(args.api_key)
        display.success(f"API key saved for {config.provider}")
        display.warning(
            "API key stored in plaintext in config file (permissions 0600). "
            "For extra security, use env vars: OPENAI_API_KEY or ANTHROPIC_API_KEY"
        )
        actions_taken = True

    if args.model:
        try:
            config.set_model(args.model)
            display.success(f"Model set to: {args.model}")
            actions_taken = True
        except ValueError as e:
            display.error(str(e))
            return

    if args.base_url:
        try:
            config.set_base_url(args.base_url)
            display.success(f"Base URL set to: {args.base_url}")
            actions_taken = True
        except ValueError as e:
            display.error(str(e))
            return

    if args.list_models:
        try:
            from .ai_client import AIClient
            client = AIClient(config)
            models = client.list_models()
            if models:
                display.section("Available Models")
                for m in models:
                    current = " (current)" if m == config.get_model() else ""
                    display.info(f"  {m}{current}")
            else:
                display.warning("No models found. Pull one with: ollama pull qwen2.5-coder:3b")
        except RuntimeError as e:
            display.error(str(e))
        actions_taken = True

    if args.reset:
        config.reset()
        display.success("Configuration reset to defaults")
        actions_taken = True

    if args.show or not actions_taken:
        config.show(display)
