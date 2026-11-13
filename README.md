# IdeaForge — AI idea-to-app builder

A GitHub-native AI project generator. No Railway, VPS, always-on server, or Termux process is required.

## Flow
1. Submit an idea on the Pages website.
2. GitHub opens an Issue.
3. Owner-only Actions workflow asks Gemini to create a project draft.
4. Actions opens a pull request for code review.
5. Review the source and merge only when satisfied.
6. Merge triggers Android APK build and/or GitHub Pages website deployment.

## One-time setup
1. Repository Settings → Secrets and variables → Actions → New repository secret: **GEMINI_API_KEY**.
2. Repository Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Repository Settings → Actions → General → enable Actions and allow required workflow permissions.
4. Submit an idea while signed in as the repository owner.

## Security
- AI generation runs only for Issues opened by the repository owner.
- API key is read only from Actions secrets; it is never sent to the browser.
- AI-generated files are restricted to generated/android and generated/web.
- No build or deployment runs until the owner merges the draft PR.
- Review generated code before merging. AI-generated code can contain bugs.

## APK download
After merging, open Actions → Build approved project → completed run → Artifacts → IdeaForge-Android-APK. Artifact retention and Actions usage are subject to GitHub plan limits.

## Notes
Gemini model availability and quotas, GitHub Actions minutes, and free-tier policies can change. The first generated Android project should be treated as a test build; inspect logs if Gradle reports a dependency or SDK issue.
