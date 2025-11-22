# Pre-commit Hooks Setup Guide

## What are Pre-commit Hooks?

Pre-commit hooks automatically run code quality checks (formatting, linting) **before** you commit code. If issues are found, they either:
- **Auto-fix** them (black, isort, autoflake)
- **Block the commit** if they can't be auto-fixed (flake8)

## Setup (One-time)

### 1. Install pre-commit (if not already installed)
```bash
pip install pre-commit
```

### 2. Install the git hooks
```bash
pre-commit install
```

That's it! Now every time you commit, the hooks will run automatically.

## What Runs on Commit?

When you run `git commit`, these checks run automatically:

1. **autoflake** - Removes unused imports and variables
2. **black** - Formats code to consistent style
3. **isort** - Sorts imports alphabetically
4. **flake8** - Lints code for errors and style issues

## How It Works

### Normal Flow:
```bash
git add .
git commit -m "your message"
# Hooks run automatically here
# If issues found, they're auto-fixed and you need to commit again
# If flake8 finds errors, commit is blocked - fix them first
```

### If Hooks Auto-fix Files:
```bash
git add .
git commit -m "your message"
# Hooks run and fix files
# You'll see: "Files were modified by this hook"
# Just add the fixed files and commit again:
git add .
git commit -m "your message"  # This time it will succeed
```

### If Flake8 Finds Errors:
```bash
git commit -m "your message"
# Flake8 finds errors
# Commit is blocked - fix the errors first
# Then commit again
```

## Manual Testing

### Test hooks on all files:
```bash
pre-commit run --all-files
```

### Test hooks on staged files only:
```bash
pre-commit run
```

### Skip hooks (not recommended):
```bash
git commit --no-verify -m "your message"
```

## Troubleshooting

### Hooks not running?
1. Make sure hooks are installed: `pre-commit install`
2. Check if `.git/hooks/pre-commit` exists
3. Reinstall: `pre-commit uninstall && pre-commit install`

### Hooks too slow?
- They only run on changed files by default
- First run is slower (downloads tools)
- Subsequent runs are cached and fast

### Want to update hook versions?
```bash
pre-commit autoupdate
```

## Configuration

Hooks are configured in `.pre-commit-config.yaml`. Current hooks:
- **autoflake** - Removes unused code
- **black** - Code formatter
- **isort** - Import sorter
- **flake8** - Linter

## CI/CD Integration

The same hooks run in CI (GitHub Actions) via:
```yaml
- name: Run pre-commit hooks
  run: pre-commit run --all-files --show-diff-on-failure
```

This ensures code quality is consistent between local and CI.

