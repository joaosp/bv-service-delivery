---
description: Generate daily changelog with git history and file changes
allowed_tools: [Bash, Write, Read, LS, Glob]
---

Generate a comprehensive changelog for today's date including:

1. **Create changelogs directory if it doesn't exist**
   - Create `changelogs/` directory in the project root

2. **Gather git information for the last 24 hours**
   - Get all commits from the last 24 hours with detailed information
   - Show commit hashes, authors, dates, and messages
   - Parse commit messages for conventional commit types (feat, fix, docs, chore, etc.)

3. **Analyze current repository state**
   - Show current branch and status
   - List modified, added, and deleted files
   - Include any staged/unstaged changes

4. **Generate changelog file**
   - Create `changelogs/YYYY-MM-DD.md` with today's date
   - Group commits by type (Features, Bug Fixes, Documentation, etc.)
   - Include file change statistics
   - Add summary of uncommitted changes if any

5. **Format the output**
   - Use proper markdown formatting
   - Include commit links/hashes for reference
   - Add timestamps and author information
   - Show file modification counts

Please create the changelog file with today's date and include all relevant changes from the repository.