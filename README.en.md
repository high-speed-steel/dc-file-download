# Discord DM Attachment Downloader

[繁體中文](README.md)

This bot processes attachment messages sent by the single Discord user configured in `config.json`. Keep your bot token only in your local `config.json`. Never post it in chat, screenshots, or a source repository.

### Requirements

- Windows 10/11 or Linux
- Python 3.10 or newer
- A Discord account with access to the [Discord Developer Portal](https://discord.com/developers/applications) to create an application and bot

### Windows setup

1. Install Python 3.10 or newer and select **Add Python to PATH** during installation.
2. Copy `config.example.json` in this folder and name the copy `config.json`.
3. In `config.json`, enter your bot token, your Discord user ID, the interaction timeout, and writable absolute paths. The first entry in `default_paths` is the fallback location.
4. Open PowerShell in this folder, create a virtual environment, and install dependencies:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   If PowerShell blocks script activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that window and activate again. The setting ends when the window closes. Alternatively, skip activation and run `& .venv\Scripts\python.exe -m pip install -r requirements.txt`, then start the bot with `& .venv\Scripts\python.exe bot.py`.
5. Start it with `python bot.py`. The log message “已登入 Discord” means the bot connected. Keep the terminal open while it runs.
6. Send an attachment to the bot in a Discord DM. First choose a saved path, enter a path manually, or select **直接下載** (Download now) to save immediately under the first default path in a `YYYY-MM-DD` folder. The second step offers the base folder, a date folder, or a custom folder. Both menus have a Cancel button. Close a manual-entry modal with its top-right **X**, then you can still cancel from the original menu. Cancelling stops the batch without downloading or invoking timeout fallback. If the flow times out, files go into a date folder under the first default path.
7. After editing saved paths or the timeout in `config.json`, run `/reload` in Discord to apply the settings without restarting. Only the account configured as `allowed_user_id` can use this command.

### Discord Developer Portal setup

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and select **New Application**.
2. Select **Bot** on the left and create a bot if needed. On the Bot page, use **Reset Token** / **View Token** to get its token. Treat it like a password and put it only in your local `config.json`. Reset it immediately if exposed.
3. Under **Privileged Gateway Intents**, enable **Message Content Intent** and save.
4. Open **OAuth2 → URL Generator**. Select the `bot` and `applications.commands` scopes. Select `View Channels`, `Send Messages`, and `Read Message History` bot permissions. Use the generated URL to invite the bot to a server where you can manage bots or create invites. The `applications.commands` scope registers `/reload`.
5. Open a DM with the bot (for example, select the bot from the server member list and choose **Message**). The `allowed_user_id` setting controls who can use the downloader.

**Forwarded messages:** Discord's forwarding UI and attachment availability depend on the client and message type. The bot reads regular attachments and also attempts to read attachments in native forward snapshots. Test with an image first. If the forwarded message contains only a text reference or the snapshot has no attachment, the bot cannot download the original file.

### `config.json` example

```json
{
  "bot_token": "Paste the token from the Developer Portal",
  "allowed_user_id": 123456789012345678,
  "interaction_timeout_seconds": 180,
  "default_paths": {
    "Default downloads": "D:/Downloads/Discord",
    "Work files": "D:/Projects/Incoming"
  }
}
```

To find your user ID, enable **User Settings → Advanced → Developer Mode**, then right-click your profile and select **Copy User ID**. Use absolute paths on the machine running the bot and make sure its OS account can write to them. The manual path dialog accepts paths copied from Windows File Explorer, such as `C:\Users\thy20\Downloads\Discord Files`, including surrounding quotes. The bot removes outer quotes and preserves spaces. In `config.json`, which uses JSON syntax, escape backslashes (for example, `C:\\Users\\thy20\\Downloads`) or use forward slashes (`C:/Users/thy20/Downloads`).

### Linux setup

In the project folder, create a virtual environment with `python3 -m venv .venv`, activate it, and run `pip install -r requirements.txt`. Set Linux absolute paths in `config.json`, such as `/srv/discord-downloads`. Start in the foreground with `python bot.py`. For persistent service and automatic restart, an administrator can create a systemd service using a dedicated low-privilege account with write access to the destination. Do not run the bot as root.

### Behavior and limitations

- Each attachment message starts a two-step menu. Both steps share the `interaction_timeout_seconds` countdown. On timeout, the bot uses the first default path and creates a folder for the current date.
- Each menu has a Cancel button. Close a manual-entry modal with its top-right **X**, then cancel from the original menu. Cancellation ends the batch without downloading files.
- Duplicate names keep their extensions and receive suffixes such as `-01`, `-02`, and so on.
- The bot attempts to repair common reversible UTF-8 filename corruption. If Discord replaces an attachment name with a hexadecimal identifier while providing its original display title, the bot uses that title and keeps the extension. If only PowerShell displays garbled text, check the name in File Explorer or run `$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()` before inspecting it again.
- The characters `\\ / : * ? " < > |` in custom folder names are replaced with underscores.
- `config.json` contains your token and must not be shared or committed. It is excluded by `.gitignore`. If the token is exposed, reset it in the Developer Portal.
- `/reload` reloads paths, the allow-listed user ID, and the timeout. Restart the bot if the token changes because the running connection uses the token from startup.

### Troubleshooting

- `PrivilegedIntentsRequired`: enable Message Content Intent in the Developer Portal and restart the bot.
- `config.json` not found: make sure you copied the example file and named it correctly.
- `401 Unauthorized`: the token is incorrect or was reset; update `config.json`.
- Permission or write errors: check that the path exists, the drive is available, and the OS account running the bot has write access.
