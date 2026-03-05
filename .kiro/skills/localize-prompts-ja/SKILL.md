---
name: localize-prompts-ja
description: Localize Python code prompts to Japanese and validate functionality. Use when creating Japanese versions of agent prompts or system instructions.
allowed-tools: Read, Write, Edit, Glob, Grep, ExecuteBash
---

# Localize Python Prompts to Japanese

Convert English prompts in Python code to natural Japanese, create localized versions, and validate they work correctly.

## Usage

- `/localize-prompts-ja` — Auto-detect all Python files with prompts and create Japanese versions
- `/localize-prompts-ja 01_basic/agent.py` — Localize a specific file
- `/localize-prompts-ja 01_basic 02_advanced` — Localize multiple directories
- `/localize-prompts-ja --check` — Report which files have prompts but no Japanese version

## Arguments

`$ARGUMENTS` contains optional file/directory paths and flags.

Parse `$ARGUMENTS` for:
- **Positional**: file or directory path(s) (optional)
- **--check**: Dry-run mode — only report files needing localization

## What to Localize

Target these patterns in Python code:

1. **Multi-line string prompts** (triple quotes):
   ```python
   SYSTEM_PROMPT = """
   You are a helpful assistant...
   """
   ```

2. **Inline string prompts** assigned to variables:
   ```python
   instruction = "Analyze the following data and provide insights"
   ```

3. **Prompt parameters** in function calls:
   ```python
   agent = Agent(
       system_prompt="You are an expert...",
       instruction="Please help with..."
   )
   ```

4. **Configuration dictionaries**:
   ```python
   config = {
       "system_prompt": "You are...",
       "user_message": "Please..."
   }
   ```

## What NOT to Localize

- Code comments (keep in English or leave as-is)
- Variable names, function names, class names
- Import statements
- Log messages (optional — can localize if user-facing)
- Error messages (optional — can localize if user-facing)
- File paths, URLs, API endpoints
- Technical terms in prompts (AWS service names, etc.)

## File Naming Convention

Create Japanese versions with `_ja` suffix before extension:

- `agent.py` → `agent_ja.py`
- `cost_estimator_agent.py` → `cost_estimator_agent_ja.py`
- `config.py` → `config_ja.py`

## Translation Quality Rules

### Natural Japanese for Prompts

Apply the same two-pass method as README translation:

**Pass 1**: Translate for meaning accuracy
**Pass 2**: Rewrite for natural Japanese (avoid 翻訳調)

**Prompt-specific guidelines**:
- Use polite form (です/ます) for agent instructions
- Use concise form (である/だ) for system descriptions where appropriate
- Keep technical terms in English when commonly used in Japanese tech context
- Maintain the same tone and formality level as the original
- Preserve formatting (newlines, bullet points, numbering)

### Example Translations

**System Prompt:**
```python
# English
SYSTEM_PROMPT = """
You are an AWS cost optimization expert.
Analyze the provided cost data and suggest improvements.
Be specific and actionable in your recommendations.
"""

# Japanese (GOOD)
SYSTEM_PROMPT = """
あなたはAWSコスト最適化の専門家です。
提供されたコストデータを分析し、改善案を提案してください。
推奨事項は具体的で実行可能な内容にしてください。
"""
```

**Instruction:**
```python
# English
instruction = "Review the CloudWatch metrics and identify any anomalies"

# Japanese (GOOD)
instruction = "CloudWatchメトリクスを確認し、異常を特定してください"
```

## Steps

### 1. Identify target files

If specific paths given in `$ARGUMENTS`, use those. Otherwise, find all Python files:

```
Glob: **/*.py
```

Filter for files containing prompt patterns (multi-line strings, prompt variables).

For `--check` mode, list files needing localization and stop.

### 2. Analyze each file

For each Python file:
1. Read the file content
2. Identify all prompt strings (using patterns above)
3. Check if `*_ja.py` version already exists
4. Determine if localization is needed

### 3. Create localized version

For each file needing localization:

1. **Copy the entire file** to `*_ja.py`
2. **Translate prompts** using two-pass method:
   - Pass 1: Accurate meaning
   - Pass 2: Natural Japanese
3. **Preserve all code structure**:
   - Same imports
   - Same function/class definitions
   - Same logic flow
   - Same variable names (only string values change)

### 4. Validate functionality

For each created `*_ja.py` file:

1. **Syntax check**:
   ```bash
   python -m py_compile <file_ja.py>
   ```

2. **Import check** (if it's a module):
   ```bash
   python -c "import <module_ja>"
   ```

3. **Run basic validation** (if executable):
   ```bash
   python <file_ja.py> --help
   # or
   uv run <file_ja.py> --help
   ```

4. **Report validation results**:
   - ✅ Syntax valid
   - ✅ Imports successful
   - ✅ Basic execution works
   - ❌ Error found (with details)

### 5. Self-review checklist

Before finishing each file, verify:
- [ ] All prompt strings translated to natural Japanese
- [ ] Code structure unchanged (same logic, same variables)
- [ ] Technical terms kept in English where appropriate
- [ ] File compiles without syntax errors
- [ ] Imports work correctly
- [ ] Formatting preserved (indentation, newlines)
- [ ] No translationese in prompts

### 6. Summary

Print a summary:
- Files localized (with validation status)
- Files already localized (skipped)
- Files with validation errors (need manual review)
- Total prompts translated

## Example Output

```
🔍 Scanning for Python files with prompts...

Found 3 files needing localization:
  - 01_basic/agent.py
  - 02_advanced/cost_estimator_agent.py
  - 03_tools/browser_agent.py

📝 Localizing 01_basic/agent.py...
  ✅ Created agent_ja.py
  ✅ Syntax check passed
  ✅ Import check passed
  Translated 2 prompts

📝 Localizing 02_advanced/cost_estimator_agent.py...
  ✅ Created cost_estimator_agent_ja.py
  ✅ Syntax check passed
  ✅ Import check passed
  Translated 4 prompts

📝 Localizing 03_tools/browser_agent.py...
  ✅ Created browser_agent_ja.py
  ⚠️  Syntax check passed
  ❌ Import check failed: ModuleNotFoundError: No module named 'custom_lib'
  Translated 3 prompts

Summary:
  ✅ 3 files localized
  ✅ 9 prompts translated
  ⚠️  1 file needs manual review (import error)
```

## Important Notes

- Always validate before considering the task complete
- If validation fails, report the error but don't delete the file
- Preserve the original file — never modify it
- If a `*_ja.py` already exists, ask before overwriting
- For complex agents, suggest running actual tests after localization
- Document any validation issues for manual review

## Edge Cases

- **Configuration files**: If prompts are in separate config files, localize those too
- **Template strings**: Preserve f-string syntax and variable placeholders
- **Multi-language support**: If code already has language switching, integrate properly
- **Shared constants**: If prompts are imported from other files, localize the source file first
