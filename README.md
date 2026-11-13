# IdeaForge

IdeaForge is a GitHub-native idea-to-app starter. It is designed to run without a separately managed backend, VPS, Railway service, or Termux process.

## Product flow

1. Submit an app or website idea from the GitHub Pages interface.
2. The idea is recorded as a GitHub Issue.
3. AI prepares a draft project for review.
4. You approve the draft before build or publishing workflows run.
5. GitHub Actions builds Android artifacts; GitHub Pages can publish static websites.

## Current status

This is the clean foundation and intake interface. The AI generation, review/approval, Flutter APK build, and website deployment workflows are the next implementation stages. They are not yet active.

## One-time setup

- Enable GitHub Pages for the repository, deploying from the `main` branch root.
- Enable GitHub Actions.
- Add the required AI provider key as a repository Actions secret when the generation workflow is installed. Never put API keys in frontend files.
- Keep idea-generation workflows restricted to trusted repository collaborators. Issue text is untrusted input and must never be treated as workflow instructions.

## Free-tier note

GitHub Actions and AI providers have usage limits and may change their free allowances. APK builds run on GitHub-hosted runners; no server needs to be kept running by you.
