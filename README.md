# Discord 私訊附件下載機器人

[English](README.en.md)

## 繁體中文

此 Bot 只處理 `config.json` 指定的單一 Discord 使用者，在私訊中送來的含附件訊息。請只把 Bot Token 放在本機 `config.json`，不要貼到聊天室、截圖或提交到版本控制。

### 需求

- Windows 10/11 或 Linux
- Python 3.10 以上
- Discord 帳號與可建立 Application/Bot 的 Discord Developer Portal 權限

### Windows 初次設定

1. 安裝 Python 3.10 以上版本。安裝時勾選 **Add Python to PATH**。
2. 在本資料夾複製 `config.example.json`，將副本命名為 `config.json`。
3. 在 `config.json` 填入 Bot Token、自己的 Discord 使用者 ID、逾時秒數與可寫入的絕對路徑。`default_paths` 第一筆就是逾時時使用的預設位置。
4. 開啟 PowerShell，切換到本資料夾，建立虛擬環境並安裝套件：

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   若 PowerShell 阻止啟用腳本，可在目前視窗執行 `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`，再重新啟用虛擬環境；關閉視窗後此設定即失效。也可略過啟用，直接用 `& .venv\Scripts\python.exe -m pip install -r requirements.txt` 安裝，再以 `& .venv\Scripts\python.exe bot.py` 執行。
5. 啟動：`python bot.py`。看到「已登入 Discord」表示 Bot 已連線。保持視窗開啟即持續運作。
6. 在自己的 Discord 私訊 Bot 傳送帶附件的訊息。第一階段可選常用路徑、手動輸入路徑，或按「直接下載」立即存到第一筆預設路徑下的 `YYYY-MM-DD` 資料夾；第二階段可選直接存入、日期資料夾或自訂資料夾。兩階段選單都有取消按鈕。打開手動輸入視窗後，可使用 Discord 視窗右上角 X 關閉，之後仍可按原選單的取消。取消後不會下載，也不會觸發逾時自動存檔。若未取消且逾時，附件自動進入第一個預設路徑下的 `YYYY-MM-DD` 資料夾。
7. 修改 `config.json` 的常用路徑或逾時秒數後，在 Discord 輸入 `/reload` 並執行，即可套用新設定，不必重啟 Bot。此指令只允許 `allowed_user_id` 對應的帳號使用。

### Discord Developer Portal 設定

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)，按 **New Application** 建立應用程式。
2. 左側選 **Bot**，新增 Bot（如尚未建立），在 Bot 頁面按 **Reset Token** / **View Token** 取得 Token。Token 等同密碼，只貼入本機 `config.json`。若外洩，立即重設。
3. Bot 頁面找到 **Privileged Gateway Intents**，開啟 **Message Content Intent** 並儲存。
4. 左側 **OAuth2 → URL Generator**，Scopes 勾選 `bot` 與 `applications.commands`；Bot Permissions 勾選 `View Channels`、`Send Messages`、`Read Message History`。使用產生的 URL 邀請 Bot 到你管理或可邀請 Bot 的伺服器。`applications.commands` 讓 Discord 註冊並顯示 `/reload`。
5. 先開啟與 Bot 的私訊（可從伺服器成員清單點 Bot → **Message**）。使用者白名單由 `allowed_user_id` 控制。

**關於轉傳訊息：**Discord 的轉傳外觀與附件可見性取決於客戶端和訊息型態。此程式會讀取一般附件，也會嘗試讀取 Discord 原生轉傳訊息快照中的附件。使用前請先用測試圖片確認你的 Discord 版本會把附件提供給 Bot；若轉傳後只有文字引用或快照沒有附件，Bot 無法下載原始附件。

### `config.json` 範例

```json
{
  "bot_token": "在 Developer Portal 複製的 Token",
  "allowed_user_id": 123456789012345678,
  "interaction_timeout_seconds": 180,
  "default_paths": {
    "預設主下載區": "D:/Downloads/Discord",
    "工作檔案": "D:/Projects/Incoming"
  }
}
```

使用者 ID：Discord **使用者設定 → 進階 → 開發者模式** 開啟，回到個人頭像按右鍵並選 **複製使用者 ID**。路徑請填 Bot 主機上的絕對路徑，並確認執行 Bot 的帳號有權寫入。手動路徑欄位可直接貼上檔案總管複製的 Windows 路徑，例如 `C:\Users\thy20\Downloads\Discord Files`，也可貼上帶外層雙引號的路徑；程式會移除外層引號並保留空格。`config.json` 是 JSON，反斜線須加倍（例如 `C:\\Users\\thy20\\Downloads`），或使用正斜線（`C:/Users/thy20/Downloads`）。

### Linux 啟動

在專案目錄建立虛擬環境：`python3 -m venv .venv`，啟用後執行 `pip install -r requirements.txt`，並在 `config.json` 使用 Linux 絕對路徑（例如 `/srv/discord-downloads`）。前景啟動：`python bot.py`。若要長期自動重啟，可由管理者建立 systemd service，設定專用低權限帳號及目標資料夾寫入權限；勿以 root 執行 Bot。

### 行為與限制

- 每則附件訊息啟動一個兩階段選單；全流程共用 `interaction_timeout_seconds` 倒數。逾時時使用第一筆預設路徑並建立今日日期資料夾。
- 每個互動選單都有取消按鈕；手動輸入視窗可先用右上角 X 關閉，再按原選單的取消。取消會結束該批次且不下載附件。
- 重複檔名保留副檔名並依序使用 `-01`、`-02` 等名稱。
- 程式會嘗試修正可無損辨識的常見 UTF-8 亂碼。若 Discord 將附件名稱轉為十六進位識別字且提供原始顯示名稱，程式會使用顯示名稱並保留副檔名。若只有 PowerShell 顯示亂碼，可用檔案總管檢查，或執行 `$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()` 後重看。
- 自訂資料夾名稱中的 `\\ / : * ? " < > |` 會替換成 `_`。
- `config.json` 含 Token，不應分享或提交；`.gitignore` 已排除它。若 Token 外洩，請先在 Developer Portal 重設。
- `/reload` 可重新載入路徑、白名單 ID 與逾時設定；Token 改變時仍須重啟，因登入連線使用啟動時的 Token。

### 常見問題

- `PrivilegedIntentsRequired`：在 Developer Portal 開啟 Message Content Intent 後重啟。
- 找不到 `config.json`：確認已複製範例檔並正確命名。
- `401 Unauthorized`：Token 錯誤或已重設，更新 `config.json`。
- 無法寫入：確認路徑存在、磁碟可用，且執行 Bot 的帳號有寫入權限。