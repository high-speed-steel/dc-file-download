"""Download attachments from forwarded Discord DMs for one allow-listed user."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import discord


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
INVALID_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|]')
LOGGER = logging.getLogger("discord_forward_downloader")


@dataclass(frozen=True)
class Settings:
    token: str
    allowed_user_id: int
    timeout: float
    default_paths: dict[str, Path]

    @property
    def primary_path(self) -> Path:
        return next(iter(self.default_paths.values()))


def load_settings() -> Settings:
    if not CONFIG_PATH.is_file():
        raise RuntimeError(
            f"找不到 {CONFIG_PATH}。請複製 config.example.json 並命名為 config.json，填入設定。"
        )
    try:
        raw: Any = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"讀取 config.json 失敗：{exc}") from exc
    if not isinstance(raw, dict):
        raise RuntimeError("config.json 最外層必須是 JSON 物件。")

    token = raw.get("bot_token")
    if not isinstance(token, str) or not token.strip() or token == "DISCORD_BOT_TOKEN_HERE":
        raise RuntimeError("請在 config.json 的 bot_token 填入 Discord Bot Token。")
    try:
        user_id = int(raw["allowed_user_id"])
        timeout = float(raw.get("interaction_timeout_seconds", 180))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("allowed_user_id 必須是數字，逾時秒數必須是正數。") from exc
    if user_id <= 0 or timeout <= 0:
        raise RuntimeError("allowed_user_id 與 interaction_timeout_seconds 必須大於 0。")
    paths = raw.get("default_paths")
    if not isinstance(paths, dict) or not paths:
        raise RuntimeError("default_paths 必須至少包含一筆『路徑名稱: 絕對路徑』。")
    resolved: dict[str, Path] = {}
    for label, value in paths.items():
        if not isinstance(label, str) or not label.strip() or not isinstance(value, str) or not value.strip():
            raise RuntimeError("default_paths 的名稱與路徑都必須是非空字串。")
        path = Path(os.path.expandvars(os.path.expanduser(value))).resolve()
        if not path.is_absolute():
            raise RuntimeError(f"預設路徑必須是絕對路徑：{value}")
        resolved[label] = path
    return Settings(token.strip(), user_id, timeout, resolved)


def safe_folder_name(value: str) -> str:
    cleaned = INVALID_FOLDER_CHARS.sub("_", value).strip().strip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("資料夾名稱不可為空白或只有點號。")
    return cleaned[:120]


def parse_user_path(value: str) -> Path:
    """Parse a pasted Windows or POSIX absolute path without losing spaces."""
    cleaned = value.strip().strip('"').strip()
    if not cleaned:
        raise ValueError("路徑不可空白。")
    cleaned = os.path.expandvars(os.path.expanduser(cleaned))
    # Windows accepts both slash styles. On Windows pathlib normalizes copied
    # Explorer paths such as C:\\Users\\name\\Downloads directly.
    path = Path(cleaned)
    if not path.is_absolute():
        raise ValueError("請貼上完整的絕對路徑，例如 C:\\Users\\name\\Downloads。")
    return path.resolve()


def repair_mojibake_filename(filename: str) -> str:
    """Conservatively repair common UTF-8-as-legacy-codepage filename corruption."""
    name = Path(filename).name.strip()
    # Typical UTF-8 decoded as Latin-1/Windows-1252 produces sequences such as
    # "æ¸¬è©¦". Only accept a reversible candidate when it removes these markers
    # and yields CJK characters; otherwise preserve Discord's original name.
    markers = ("Ã", "Â", "æ", "å", "ç", "è", "é", "ï¿½", "�")
    if not any(marker in name for marker in markers):
        return name
    for legacy_encoding in ("cp1252", "latin-1"):
        try:
            candidate = name.encode(legacy_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        cjk_count = sum("\u3400" <= char <= "\u9fff" for char in candidate)
        if cjk_count and not any(marker in candidate for marker in markers):
            return candidate
    return name


def attachment_filename(attachment: discord.Attachment) -> str:
    """Use Discord's title when filename was replaced by an opaque upload key."""
    filename = repair_mojibake_filename(attachment.filename)
    stem = Path(filename).stem
    title = getattr(attachment, "title", None)
    if title and re.fullmatch(r"[0-9a-fA-F]{16,}", stem):
        # Discord may normalize an unsupported filename into a generated
        # hexadecimal storage name while preserving its display title.
        title = repair_mojibake_filename(title).strip()
        if title:
            suffix = Path(filename).suffix
            restored = title if Path(title).suffix else f"{title}{suffix}"
            return INVALID_FOLDER_CHARS.sub("_", restored)
    return filename


def unique_destination(directory: Path, filename: str) -> Path:
    """Return an unused path, adding -01, -02, ... before the extension."""
    name = repair_mojibake_filename(filename)
    if not name or name in {".", ".."}:
        name = "attachment"
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 1
    while True:
        candidate = directory / f"{stem}-{index:02d}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024**2:.2f} MB"


def attachment_list(message: discord.Message) -> list[discord.Attachment]:
    # A native forward can include attachments in its snapshots. Also include
    # ordinary message attachments, while avoiding duplicate attachment IDs.
    found: dict[int, discord.Attachment] = {item.id: item for item in message.attachments}
    for snapshot in getattr(message, "message_snapshots", ()):
        for item in getattr(snapshot, "attachments", ()):
            found[item.id] = item
    return list(found.values())


class BasePathSelect(discord.ui.Select):
    def __init__(self, flow: "DownloadFlow") -> None:
        self.flow = flow
        options = [
            discord.SelectOption(label=label[:100], value=str(index), description=str(path)[:100])
            for index, (label, path) in enumerate(flow.settings.default_paths.items())
        ]
        super().__init__(placeholder="選擇儲存位置", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.flow.choose_base(interaction, list(self.flow.settings.default_paths.values())[int(self.values[0])])


class BasePathView(discord.ui.View):
    def __init__(self, flow: "DownloadFlow") -> None:
        super().__init__(timeout=None)
        self.flow = flow
        self.add_item(BasePathSelect(flow))

    @discord.ui.button(label="手動輸入路徑", style=discord.ButtonStyle.secondary, row=1)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ManualPathModal(self.flow))

    @discord.ui.button(label="直接下載", style=discord.ButtonStyle.primary, row=1)
    async def direct_download(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        destination = self.flow.settings.primary_path / date.today().isoformat()
        await self.flow.finish(interaction, destination, timed_out=False)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.flow.cancel(interaction)


class ManualPathModal(discord.ui.Modal, title="輸入儲存路徑"):
    path = discord.ui.TextInput(
        label="絕對路徑", placeholder="例如 D:/Downloads 或 /mnt/storage/downloads", max_length=500
    )

    def __init__(self, flow: "DownloadFlow") -> None:
        super().__init__(timeout=flow.settings.timeout)
        self.flow = flow

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            path = parse_user_path(str(self.path))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self.flow.choose_base(interaction, path)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        LOGGER.error("路徑輸入視窗發生錯誤：%s", error, exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message("路徑輸入發生錯誤，請取消本次流程後重試。", ephemeral=True)


class FolderChoiceView(discord.ui.View):
    def __init__(self, flow: "DownloadFlow") -> None:
        super().__init__(timeout=None)
        self.flow = flow

    @discord.ui.button(label="直接存入", style=discord.ButtonStyle.primary)
    async def direct(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.flow.finish(interaction, self.flow.base_path, timed_out=False)

    @discord.ui.button(label="建立今日日期資料夾", style=discord.ButtonStyle.secondary)
    async def today(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.flow.finish(interaction, self.flow.base_path / date.today().isoformat(), timed_out=False)

    @discord.ui.button(label="自訂資料夾名稱", style=discord.ButtonStyle.secondary)
    async def custom(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ManualFolderModal(self.flow))

    @discord.ui.button(label="取消", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.flow.cancel(interaction)


class ManualFolderModal(discord.ui.Modal, title="建立自訂資料夾"):
    name = discord.ui.TextInput(label="資料夾名稱", placeholder="例如：專案文件", max_length=120)

    def __init__(self, flow: "DownloadFlow") -> None:
        super().__init__(timeout=flow.settings.timeout)
        self.flow = flow

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            folder = safe_folder_name(str(self.name))
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self.flow.finish(interaction, self.flow.base_path / folder, timed_out=False)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        LOGGER.error("資料夾名稱輸入視窗發生錯誤：%s", error, exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message("輸入發生錯誤，請取消本次流程後重試。", ephemeral=True)


class DownloadFlow:
    def __init__(self, bot: discord.Client, message: discord.Message, attachments: list[discord.Attachment], settings: Settings) -> None:
        self.bot = bot
        self.message = message
        self.attachments = attachments
        self.settings = settings
        self.base_path: Path | None = None
        self.prompt: discord.Message | None = None
        self.lock = asyncio.Lock()
        self.completed = False
        self.timeout_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.prompt = await self.message.channel.send(
            f"收到 {len(self.attachments)} 個附件。請選擇基礎儲存路徑（{self.settings.timeout:g} 秒內操作；手動輸入視窗可按取消關閉）：",
            view=BasePathView(self),
        )
        self.timeout_task = asyncio.create_task(self._expire())

    async def _expire(self) -> None:
        try:
            await asyncio.sleep(self.settings.timeout)
            async with self.lock:
                if self.completed:
                    return
                self.completed = True
            await self._disable_prompt()
            destination = self.settings.primary_path / date.today().isoformat()
            await self._download(destination, timed_out=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("逾時自動存檔失敗")
            await self._notify_error("逾時自動存檔失敗，請確認預設路徑可寫入及磁碟空間充足。")

    async def _disable_prompt(self) -> None:
        if self.prompt is None:
            return
        try:
            await self.prompt.edit(view=None)
        except discord.HTTPException:
            LOGGER.debug("無法移除互動訊息元件", exc_info=True)

    async def choose_base(self, interaction: discord.Interaction, path: Path) -> None:
        async with self.lock:
            if self.completed:
                await interaction.response.send_message("這次下載流程已結束。", ephemeral=True)
                return
            self.base_path = path
        await interaction.response.edit_message(
            content=f"儲存位置：`{path}`\n請選擇是否建立子資料夾：", view=FolderChoiceView(self)
        )

    async def finish(self, interaction: discord.Interaction, destination: Path, timed_out: bool) -> None:
        async with self.lock:
            if self.completed:
                await interaction.response.send_message("這次下載流程已結束。", ephemeral=True)
                return
            self.completed = True
        if self.timeout_task:
            self.timeout_task.cancel()
        await interaction.response.edit_message(content="正在下載附件，請稍候…", view=None)
        await self._download(destination, timed_out=timed_out)

    async def cancel(self, interaction: discord.Interaction) -> None:
        async with self.lock:
            if self.completed:
                await interaction.response.send_message("這次下載流程已結束。", ephemeral=True)
                return
            self.completed = True
        if self.timeout_task:
            self.timeout_task.cancel()
        await interaction.response.edit_message(content="已取消這次下載；沒有儲存附件。", view=None)

    async def _download(self, destination: Path, timed_out: bool) -> None:
        try:
            destination.mkdir(parents=True, exist_ok=True)
            if not destination.is_dir():
                raise OSError("目標路徑不是資料夾。")
            saved: list[tuple[str, int]] = []
            for attachment in self.attachments:
                original_name = attachment.filename
                download_name = attachment_filename(attachment)
                if download_name != original_name:
                    LOGGER.info("已還原附件顯示檔名：%r -> %r", original_name, download_name)
                target = unique_destination(destination, download_name)
                await attachment.save(target)
                saved.append((target.name, target.stat().st_size))
            mode = "操作逾時，已自動啟用預設存檔機制" if timed_out else "✅ 下載操作完成"
            lines = [mode, f"儲存目錄：`{destination}`", "檔案明細："]
            lines.extend(f"• `{name}` — {format_size(size)}" for name, size in saved)
            await self.message.channel.send("\n".join(lines))
        except (OSError, discord.HTTPException) as exc:
            LOGGER.exception("下載附件失敗")
            await self._notify_error(f"下載失敗：{exc}")

    async def _notify_error(self, detail: str) -> None:
        try:
            await self.message.channel.send(f"⚠️ {detail}")
        except discord.HTTPException:
            LOGGER.exception("無法傳送錯誤通知")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    active_settings = load_settings()
    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)
    command_tree = discord.app_commands.CommandTree(bot)
    seen_message_ids: set[int] = set()

    @command_tree.command(name="reload", description="重新載入下載路徑與互動逾時設定")
    async def reload_settings(interaction: discord.Interaction) -> None:
        nonlocal active_settings
        if interaction.user.id != active_settings.allowed_user_id:
            await interaction.response.send_message("你沒有權限使用此指令。", ephemeral=True)
            return
        try:
            new_settings = load_settings()
        except RuntimeError as exc:
            await interaction.response.send_message(f"設定重新載入失敗：{exc}", ephemeral=True)
            return
        if new_settings.token != active_settings.token:
            await interaction.response.send_message(
                "設定檔中的 Token 已變更；為避免回報成功但仍使用舊連線，請重新啟動 Bot 套用新 Token。",
                ephemeral=True,
            )
            return
        active_settings = new_settings
        await interaction.response.send_message(
            f"設定已重新載入。常用路徑：{len(active_settings.default_paths)} 個；"
            f"互動逾時：{active_settings.timeout:g} 秒。",
            ephemeral=True,
        )

    @bot.event
    async def on_ready() -> None:
        LOGGER.info("已登入 Discord：%s (ID: %s)", bot.user, bot.user.id if bot.user else "?")
        try:
            synced = await command_tree.sync()
            LOGGER.info("已同步 %s 個應用程式指令", len(synced))
        except discord.HTTPException:
            LOGGER.exception("同步應用程式指令失敗")

    @bot.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot or message.author.id != active_settings.allowed_user_id:
            return
        attachments = attachment_list(message)
        if not attachments:
            return
        if message.id in seen_message_ids:
            return
        seen_message_ids.add(message.id)
        if len(seen_message_ids) > 5000:
            seen_message_ids.clear()
            seen_message_ids.add(message.id)
        flow = DownloadFlow(bot, message, attachments, active_settings)
        try:
            await flow.start()
        except discord.HTTPException:
            LOGGER.exception("無法建立下載互動選單")

    bot.run(active_settings.token, log_handler=None)


if __name__ == "__main__":
    main()
