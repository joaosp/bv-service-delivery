# Weekly Progress Report Generator

Generate comprehensive weekly progress reports and create Linear tasks automatically.

## Usage

```
/weekly-report [next-steps-description]
```

**Example:**
```
/weekly-report "Complete Azure AD integration testing and deploy to production environment"
```

## Report Meta-Structure

Based on analysis of BRO-5 (Week 37) and BRO-6 (Week 38), the weekly report follows this pattern:

### 1. Completed ✅
- **Major Features**: New implementations, integrations
- **Infrastructure**: Setup, configurations, tooling
- **Bug Fixes**: Issues resolved, improvements made
- **Documentation**: READMEs, setup guides, specifications
- **Quantified Results**: Files created, lines of code, processing improvements

### 2. Key Metrics 📊
- **Processing Speed**: Performance improvements
- **Accuracy Rates**: Success percentages, error reduction
- **Data Volume**: Records processed, files handled
- **Automation Impact**: Time saved, efficiency gains
- **Technical Coverage**: Objects supported, APIs integrated

### 3. Technical Achievements 🔧
- **Architecture**: New patterns, modular designs
- **API Integration**: External services connected
- **Query Optimization**: SOQL improvements, caching
- **Error Handling**: Robustness improvements
- **Code Quality**: Refactoring, best practices

### 4. Deliverables 📦
- **Code Files**: New modules, scripts created
- **Documentation**: Setup guides, API references
- **Configuration**: Templates, requirements files
- **Outputs**: Generated reports, processed data

### 5. Next Steps 🎯
- Forward-looking tasks (from command argument)
- Identified improvements
- Planned features
- Technical debt to address

## Git Analysis Commands

Use these git commands to extract weekly progress data:

### Commit Summary
```bash
# Get all commits from the last 7 days with stats
git log --since="1 week ago" --pretty=format:"%h - %s (%ar)" --stat

# Get just the commit messages for quick scanning
git log --since="1 week ago" --oneline
```

### Feature Analysis
```bash
# Find feature additions
git log --since="1 week ago" --pretty=format:"- %s" --grep="feat:"

# Find bug fixes
git log --since="1 week ago" --pretty=format:"- %s" --grep="fix:"

# Find documentation updates
git log --since="1 week ago" --pretty=format:"- %s" --grep="docs:"
```

### File Changes
```bash
# Get file change statistics
git diff --stat HEAD~$(git rev-list --count HEAD --since="1 week ago")

# List all files modified this week
git diff --name-only HEAD~$(git rev-list --count HEAD --since="1 week ago")

# Count lines added/removed
git log --since="1 week ago" --numstat --pretty=format:"" | awk '{added+=$1; removed+=$2} END {print "Lines added:", added, "Lines removed:", removed}'
```

### File Type Analysis
```bash
# Python files created/modified
git diff --name-only HEAD~$(git rev-list --count HEAD --since="1 week ago") | grep -E "\.py$" | wc -l

# Documentation files
git diff --name-only HEAD~$(git rev-list --count HEAD --since="1 week ago") | grep -E "\.md$" | wc -l

# Configuration files
git diff --name-only HEAD~$(git rev-list --count HEAD --since="1 week ago") | grep -E "\.(json|yml|yaml|txt)$" | wc -l
```

## Linear MCP Commands

### Get Current Week Number
```bash
# Calculate week number from current date
echo "Week $(date +%V)"
```

### Check Previous Week's Task
```bash
# List recent issues to find last week's task
mcp__linear-server__list_issues --limit 10 --assignee "me" --orderBy "updatedAt"
```

### Create This Week's Task
```javascript
// Use this pattern to create the weekly task
mcp__linear-server__create_issue {
  "title": "Week [NUMBER] - [PRIMARY_ACHIEVEMENT]",
  "description": "[GENERATED_REPORT_MARKDOWN]",
  "team": "Broadvoice AI", 
  "project": "Extraction of parameters from Call Transcriptions",
  "assignee": "me"
}
```

## Implementation Steps

When running this command:

1. **Calculate Week Number**: `date +%V`

2. **Gather Git Data**:
   - Run commit analysis commands above
   - Count files created/modified by type
   - Calculate lines added/removed
   - Identify major features from commit messages

3. **Structure the Report**:
   - **Completed**: Extract from commit messages and file changes
   - **Metrics**: Calculate from git stats and file counts
   - **Technical Achievements**: Identify from code changes and new files
   - **Deliverables**: List new files and major modifications
   - **Next Steps**: Use command argument + identified improvements

4. **Create Linear Task**:
   - Title: "Week {week_number} - {primary_achievement}"
   - Description: Full markdown report
   - Assign to current user
   - Set project and team

5. **Output**: Show Linear task URL and summary

## Example Output Format

```markdown
## Completed ✅

### Microsoft Teams Integration
- Implemented Microsoft Graph API integration for transcript extraction
- Added VideoCall object support to Salesforce extractors  
- Created modular extraction architecture with 9 specialized modules
- Fixed SOQL field errors (removed non-existent Description field)

### Infrastructure & Documentation
- Added comprehensive Azure AD setup documentation (TEAMS_SETUP.md)
- Created requirements.txt with Graph API dependencies
- Updated CLAUDE.md with new pipeline information

## Key Metrics 📊
- **Files Created**: 12 new Python modules
- **Lines Added**: 5,202 lines of code
- **Processing Enhancement**: Added VideoCall support (previously VoiceCall only)
- **Integration Coverage**: Now supports Teams, VoiceCall, MessagingSession

## Technical Achievements 🔧
- **Authentication**: MSAL integration with Azure AD
- **API Integration**: Microsoft Graph API for transcript retrieval
- **Data Parsing**: Base64 decode Teams meeting identifiers
- **Error Handling**: Fixed 3 critical SOQL field errors

## Deliverables 📦
- salesforce_extractors/ - Complete modular package (9 modules)
- TEAMS_SETUP.md - Azure AD configuration guide
- requirements.txt - Python dependencies
- Git commit: feat: Add VideoCall support with Microsoft Teams transcript extraction

## Next Steps 🎯
[From command argument]
```

This command provides a complete framework for consistent weekly progress reporting with quantified results and proper Linear task creation.