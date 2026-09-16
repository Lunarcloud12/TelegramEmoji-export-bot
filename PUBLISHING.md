# Publishing to GitHub

The project owner creates the repository and uploads the source code. Preparing the source archive does not publish anything automatically.

1. Run the checks in CONTRIBUTING.md.
2. Run `python scripts/package_source.py`. The archive is written to `dist/emoji-export-bot-source.zip`. It includes an empty `.env.example`, source code, tests, documentation, the MIT license, and GitHub Actions. It excludes `.env`, `data`, `.venv`, `.git`, logs, and test output.
3. Create an empty repository on GitHub, for example `emoji-export-bot`.
4. Extract the archive and upload **its contents**, including the hidden `.github` directory. GitHub Desktop or Git makes it easier to include hidden files. The ZIP can also be attached to a release, but it does not replace source files in the repository.
5. To upload using Git from the extracted directory:

```sh
git init -b main
git add .
git diff --cached --stat
git commit -m "Prepare configurable emoji export bot"
# Replace the placeholder with the repository URL provided by GitHub:
git remote add origin <your-repository-url>
git push -u origin main
```

6. Wait for the first Actions run. CI checks Python 3.12 on Windows/Linux, conversion, source packaging, and the Docker build. CI status remains unverified until it runs on GitHub.
7. Optionally create a `v0.2.2` release using CHANGELOG.md.

Suggested description: **Telegram bot that exports emoji and stickers to GIF, MP4, transparent WebM/MOV and PNG with per-user export settings.**

Run the bot on a computer or server. GitHub stores the source and runs checks; this workflow does not provide continuous bot hosting. Tests do not require a bot token in GitHub Secrets.
