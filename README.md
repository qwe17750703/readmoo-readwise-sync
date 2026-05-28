# Readmoo → Readwise 一鍵同步

把 Readmoo（讀墨）所有書籍的畫線，**一次** 全部串接同步到 Readwise

Readmoo 官方的 Readwise 整合每次只能匯出一本書，藏書多了會很痛苦。這個工具一次抓完所有書的畫線，再批次推送到 Readwise，第二次以後只處理有變動的書，速度極快。

## 功能

- **全書批次同步**：一次處理整個書架
- **增量同步**：用本機快取記錄每本書的畫線數，沒變的書直接略過，下次執行的時候會跑很快，因為已經在本地端建立快取。
- **每日自動執行**：附 Windows 工作排程器設定腳本
- **失敗通知**：Token 過期或寫入失敗會跳 Windows toast 通知
- **失敗補救**：Readwise 整批退回時自動逐筆重送，把好的畫線救回來
- **自動截斷**：超過 Readwise 8191 字元上限的畫線自動截斷
- **去重複**：Readwise 端依 title/author/text 自動去重複的部分

## 系統需求

- Python 3.9+
- Windows（通知與排程功能）／macOS / Linux（通知功能會自動 no-op）

## 安裝

```bash
git clone https://github.com/<你的帳號>/readmooProject.git
cd readmooProject
pip install -r requirements.txt
```

## 設定

複製設定檔範本並填入兩個 token：

```bash
copy .env.example .env       # Windows
cp .env.example .env         # macOS / Linux
```

編輯 `.env`：

```
READMOO_TOKEN=你的_readmoo_bearer_token
READWISE_TOKEN=你的_readwise_access_token
```

### 取得 Readmoo Bearer Token

Readmoo 沒有公開 API，token 要從瀏覽器抓：

1. 用瀏覽器登入 [readmoo.com](https://readmoo.com)
2. 按 `F12` 開啟開發者工具 → 切到「Network（網路）」分頁
3. 重新整理頁面或點進任一本書
4. 在 Network 列表中找任何發送到 `api.readmoo.com` 的請求
5. 點進去 → 切到「Headers（標頭）」分頁
6. 往下拉找到 `Authorization: Bearer xxxxx...`，複製 `Bearer ` 後面那一長串

> **注意**：這個 token 會過期（通常幾天到幾週），失效時程式會跳通知提醒你重新抓一次。

### 取得 Readwise Token

到 [readwise.io/access_token](https://readwise.io/access_token) 直接複製。

## 使用方式

### 手動執行

```bash
python main.py
```

第一次跑會處理整個書架，之後跑只會處理畫線數有變動的書。

### 強制重抓

當你覺得快取可能不準（例如刪了 1 條畫線又加了 1 條，總數不變）：

```bash
python main.py --force
```

### 排程模式（無互動）

```bash
python main.py --silent
```

缺 token 或失敗時不會等待輸入，直接結束並跳通知。給排程器用。

## 設定每日自動同步（Windows）

在 PowerShell 進入專案資料夾後：

```powershell
# 預設每天早上 9:00
.\setup_schedule.ps1

# 自訂時間
.\setup_schedule.ps1 -Time "21:30"

# 移除排程
.\setup_schedule.ps1 -RemoveOnly
```

## 在哪裡看到匯入的畫線？

匯入到的是 **Readwise 經典版**（不是 Reader）：

- 網頁：[readwise.io/library](https://readwise.io/library) 或 [readwise.io/books](https://readwise.io/books)
- 手機 App：Readwise → Books
- 來源篩選會顯示 `Readmoo`

## 專案結構

```
readmooProject/
├── main.py                # CLI 進入點
├── requirements.txt       # Python 套件清單
├── .env.example           # 設定檔範本
├── run_sync.bat           # Windows 工作排程器進入點
├── setup_schedule.ps1     # 註冊／移除排程的腳本
└── src/
    ├── readmoo.py         # Readmoo 非公開 API 客戶端
    ├── readwise.py        # Readwise API 客戶端（截斷 + 補救邏輯）
    ├── cache.py           # 增量同步的本機快取
    └── notify.py          # Windows toast 通知
```

執行時會產生（已加入 `.gitignore`）：

- `.sync_cache.json` — 每本書上次同步時的畫線數
- `sync.log` — 執行紀錄，自動輪替

## 增量同步是怎麼運作的？

1. 取得 Readmoo 書單
2. 對每本書，先做一個超輕量的 API call **只查畫線總數**
3. 跟本機快取比對：
   - **數量一致** → 整本略過（省下 N 個分頁 API call）
   - **數量變了或全新的書** → 抓完整畫線內容
4. 推送到 Readwise（自動去重）
5. 寫入快取，紀錄每本書最新的畫線數

只有「Readwise 寫入成功」的書才會進快取；失敗的書下次自動重試。

## 已知限制

- **Readmoo Token 會過期**：失效時需要重新從瀏覽器 DevTools 抓一次
- **單條畫線超過 8191 字** 會被截斷加 `…`（Readwise 硬性上限）
- **「刪 1 條 + 加 1 條」造成總數不變**：增量同步會略過這本書，要跑 `--force` 才會抓到變更
- **沒有真正的「即時同步」**：靠定時排程

## 授權

自由使用、修改、散布。

