# Security and data handling

The Telegram token is stored in `.env` or the `BOT_TOKEN` environment variable. It is excluded from the source archive and Docker image, and ignored by Git. If a token has already been published, replace it through @BotFather.

`data/settings.sqlite3` stores only Telegram user IDs and export preferences. Resetting settings through `/settings` deletes the saved record. Messages and media are not stored in the database. Temporary files are deleted after processing; an unexpected process termination may leave files in the operating system's temporary directory.

Each settings panel belongs to its requesting user. Other users cannot change its preferences. Conversion runs in a separate process with a time limit. Input size, duration, dimensions, and concurrency limits help control resource usage. This is not a complete sandbox for untrusted native codecs: run public instances in an unprivileged container and keep dependencies updated.

Report security issues privately to the repository owner, or use GitHub private vulnerability reporting if it is enabled. Do not post active tokens or private media in public issues.
