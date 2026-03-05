---
name: localize-comments-ja
description: Localize Python code comments to Japanese while preserving prompts and code. Use when creating Japanese versions with localized comments for better readability.
allowed-tools: Read, Write, Edit, Glob, Grep, ExecuteBash
---

# Localize Python Comments to Japanese

Convert English comments in Python code to natural Japanese, create localized versions, and validate they work correctly.

## Usage

- `/localize-comments-ja` — Auto-detect all Python files and create Japanese comment versions
- `/localize-comments-ja 01_basic/agent.py` — Localize a specific file
- `/localize-comments-ja 01_basic 02_advanced` — Localize multiple directories
- `/localize-comments-ja --check` — Report which files need localization

## Arguments

`$ARGUMENTS` contains optional file/directory paths and flags.

Parse `$ARGUMENTS` for:
- **Positional**: file or directory path(s) (optional)
- **--check**: Dry-run mode — only report files needing localization

## What to Localize

Target these comment patterns in Python code:

1. **Single-line comments**:
   ```python
   # This is a comment
   x = 5  # Inline comment
   ```

2. **Docstrings** (module, class, function):
   ```python
   """
   This is a docstring explaining the function.
   
   Args:
       param: Description
   """
   ```

3. **Multi-line comments**:
   ```python
   # This is a longer explanation
   # that spans multiple lines
   # to describe complex logic
   ```

## What NOT to Localize

- **Prompt strings** (already handled by localize-prompts-ja skill):
  - SYSTEM_PROMPT, instruction, user-facing messages
- **Code** (variable names, function names, class names)
- **Import statements**
- **String literals** that are not prompts or comments
- **URLs, file paths, API endpoints**
- **Technical identifiers** in comments (e.g., "AWS", "EC2", "AgentCore")
- **Code examples within comments** (keep code as-is, translate explanation only)

## File Naming Convention

Create Japanese comment versions with `_comments_ja` suffix before extension:

- `agent.py` → `agent_comments_ja.py`
- `cost_estimator_agent.py` → `cost_estimator_agent_comments_ja.py`
- `test_memory.py` → `test_memory_comments_ja.py`

## Translation Quality Rules

### Natural Japanese for Comments

Apply the same two-pass method as README translation:

**Pass 1**: Translate for meaning accuracy
**Pass 2**: Rewrite for natural Japanese (avoid 翻訳調)

**Comment-specific guidelines**:
- Use concise, clear Japanese appropriate for code comments
- Maintain the same level of detail as the original
- Keep technical terms in English when commonly used in Japanese development
- Preserve comment formatting (indentation, alignment)
- For docstrings, maintain Args/Returns/Raises structure

### Example Translations

**Single-line comment:**
```python
# English
# Initialize the agent with default settings

# Japanese (GOOD)
# デフォルト設定でエージェントを初期化
```

**Inline comment:**
```python
# English
max_retries = 3  # Retry up to 3 times on failure

# Japanese (GOOD)
max_retries = 3  # 失敗時は最大3回リトライ
```

**Docstring:**
```python
# English
def estimate_costs(self, architecture_description: str) -> str:
    """
    Estimate costs for a given architecture description
    
    Args:
        architecture_description: Description of the system to estimate
        
    Returns:
        Cost estimation results as string
    """

# Japanese (GOOD)
def estimate_costs(self, architecture_description: str) -> str:
    """
    指定されたアーキテクチャの説明に基づいてコストを見積もります
    
    Args:
        architecture_description: 見積もり対象のシステムの説明
        
    Returns:
        コスト見積もり結果を文字列として返します
    """
```

**Multi-line comment with code example:**
```python
# English
# Configure logging for debugging:
#   logging.basicConfig(level=logging.DEBUG)
# This will show all agent operations

# Japanese (GOOD)
# デバッグ用のロギング設定:
#   logging.basicConfig(level=logging.DEBUG)
# これにより全てのエージェント操作が表示されます
```

## Steps

### 1. Identify target files

If specific paths given in `$ARGUMENTS`, use those. Otherwise, find all Python files:

```
Glob: **/*.py
```

For `--check` mode, list files needing comment localization and stop.

### 2. Analyze each file

For each Python file:
1. Read the file content
2. Identify all comments and docstrings
3. Check if `*_comments_ja.py` version already exists
4. Determine if localization is needed (skip if no comments or already localized)

### 3. Create localized version

For each file needing localization:

1. **Copy the entire file** to `*_comments_ja.py`
2. **Translate comments and docstrings** using two-pass method:
   - Pass 1: Accurate meaning
   - Pass 2: Natural Japanese
3. **Preserve all code and prompts**:
   - Same code structure
   - Same variable/function/class names
   - Same prompt strings (SYSTEM_PROMPT, etc.)
   - Same imports and logic
   - Only comments change

### 4. Validate functionality

For each created `*_comments_ja.py` file:

1. **Syntax check**:
   ```bash
   python -m py_compile <file_comments_ja.py>
   ```

2. **Import check** (if it's a module):
   ```bash
   python -c "import <module_comments_ja>"
   ```

3. **Report validation results**:
   - ✅ Syntax valid
   - ✅ Imports successful
   - ❌ Error found (with details)

### 5. Self-review checklist

Before finishing each file, verify:
- [ ] All comments translated to natural Japanese
- [ ] All docstrings translated (including Args/Returns/Raises)
- [ ] Code structure unchanged
- [ ] Prompt strings unchanged (not translated)
- [ ] Technical terms kept in English where appropriate
- [ ] File compiles without syntax errors
- [ ] Formatting preserved (indentation, alignment)
- [ ] No translationese in comments

### 6. Summary

Print a summary:
- Files localized (with validation status)
- Files already localized (skipped)
- Files with validation errors (need manual review)
- Total comments translated

## Example Output

```
🔍 Scanning for Python files with comments...

Found 3 files needing comment localization:
  - 01_basic/agent.py (15 comments)
  - 02_advanced/cost_estimator_agent.py (42 comments)
  - 03_tools/browser_agent.py (28 comments)

📝 Localizing 01_basic/agent.py...
  ✅ Created agent_comments_ja.py
  ✅ Syntax check passed
  ✅ Import check passed
  Translated 15 comments

📝 Localizing 02_advanced/cost_estimator_agent.py...
  ✅ Created cost_estimator_agent_comments_ja.py
  ✅ Syntax check passed
  ✅ Import check passed
  Translated 42 comments (8 docstrings, 34 inline)

📝 Localizing 03_tools/browser_agent.py...
  ✅ Created browser_agent_comments_ja.py
  ✅ Syntax check passed
  ✅ Import check passed
  Translated 28 comments

Summary:
  ✅ 3 files localized
  ✅ 85 comments translated
  ✅ All files validated successfully
```

## Important Notes

- Always validate before considering the task complete
- Preserve the original file — never modify it
- If a `*_comments_ja.py` already exists, ask before overwriting
- Don't translate prompt strings (use localize-prompts-ja for that)
- Maintain the same comment density and detail level
- For complex technical comments, prioritize clarity over literal translation

## Edge Cases

- **Mixed language comments**: If comments already contain Japanese, improve them
- **TODO/FIXME/NOTE markers**: Keep in English, translate the description
- **License headers**: Keep in original language (usually English)
- **Auto-generated comments**: Skip or translate minimally
- **Code in comments**: Keep code as-is, translate surrounding explanation
