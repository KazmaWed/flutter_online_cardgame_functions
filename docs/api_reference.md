# API Reference

## Game Management APIs

### create_game
**Description**: 新しいゲームを作成する

**Parameters**: なし (認証必須)

**Returns**:
```json
{
  "success": true,
  "gameId": "string",
  "password": "string" // 4桁の数字文字列
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `RESOURCE_EXHAUSTED`: レート制限に達した (最大30ゲーム/60秒)
- `ALREADY_EXISTS`: パスワード生成に失敗
- `INTERNAL`: 内部エラー

---

### enter_game
**Description**: ゲームに参加する（パスワードを使用）

**Parameters**:
```json
{
  "password": "string" // 4桁の数字文字列
}
```

**Returns**:
```json
{
  "success": true,
  "gameId": "string"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: パスワードが無効 (4桁の数字文字列が必要)
- `NOT_FOUND`: パスワードが見つからない
- `FAILED_PRECONDITION`: ゲームフェーズが0以外 (マッチング中のみ参加可能)
- `RESOURCE_EXHAUSTED`: ゲームが満員 (最大12プレイヤー)
- `INTERNAL`: 内部エラー

---

### start_game
**Description**: ゲームを開始する（管理者のみ）

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Game started successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: 管理者権限がない
- `FAILED_PRECONDITION`: ゲームフェーズが0以外（マッチング中のみ開始可能）
- `INTERNAL`: 内部エラー

---

### end_game
**Description**: ゲームを終了する（管理者のみ）

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Game ended successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: 管理者権限がない
- `FAILED_PRECONDITION`: ゲームフェーズが1以外（進行中のみ終了可能）
- `INTERNAL`: 内部エラー

**Notes**:
- ゲームのphaseを2に変更します
- 管理者（最初に入室したプレイヤー）のみ実行可能です

---

### reset_game
**Description**: ゲームをリセットする（管理者のみ）

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Game reset successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: 管理者権限がない
- `FAILED_PRECONDITION`: ゲームフェーズが1または2以外（進行中または終了後のみリセット可能）
- `INTERNAL`: 内部エラー

**Notes**:
- ゲームのphaseを0に戻します
- 全プレイヤーの`hint`と`submitted`フィールドをクリアします
- `values`フィールドを削除します
- 設定データを`state/config`構造に戻します
- 管理者（最初に入室したプレイヤー）のみ実行可能です
- 全ての変更は原子的に実行されます

---

### exit_game
**Description**: ゲームから退出する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Successfully exited game"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効またはプレイヤーが参加していない
- `NOT_FOUND`: ゲームが見つからない
- `INTERNAL`: 内部エラー

**Notes**:
- 最後のプレイヤーが退出した場合、ゲームが自動的に削除されます
- パスワードマッピングも同時に削除されます

---

### init_player
**Description**: プレイヤーを初期化し、現在のゲームIDを返す

**Parameters**: なし (認証必須)

**Returns**:
```json
{
  "success": true,
  "gameId": "string" // または null
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要

---

### get_game_config
**Description**: ゲームの設定と値を取得する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "values": {
    "player-id": 42 // phase < 2では自分の値のみ、phase >= 2では全員の値
  },
  "config": {
    "topic": "string", // phase != 0のみ存在
    "playerInfo": { // phase != 0のみ存在
      "player-id": {
        "name": "string",
        "avatar": 5, // 0-11の整数
        "entrance": 1234567890 // millisecondsSinceEpoch
      }
    }
  }
}
```

**Notes**:
- `values` は phase == 0 では空のオブジェクトです
- `config.topic` と `config.playerInfo` は phase != 0 でのみ存在します

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `NOT_FOUND`: ゲームが見つからない/プレイヤーが参加していない
- `DEADLINE_EXCEEDED`: ゲームが期限切れ（30秒間非アクティブ）
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### get_game_info
**Description**: ゲーム情報を取得する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "gameId": "string",
  "password": "string" // 4桁の数字文字列
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `NOT_FOUND`: ゲーム/プレイヤーが見つからない
- `DEADLINE_EXCEEDED`: ゲームが期限切れ（30秒間非アクティブ）
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

**Notes**:
- プレイヤーが参加しているゲームの情報のみ取得可能
- ゲームのパスワードを含むため、セキュリティに注意

---

### get_value
**Description**: プレイヤーの値を取得する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "gameId": "string",
  "value": 42 // 1-100の整数
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `NOT_FOUND`: ゲーム/プレイヤー/値が見つからない
- `FAILED_PRECONDITION`: phase == 0（マッチング中は値を取得できません）
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `DEADLINE_EXCEEDED`: ゲームが期限切れ（30秒間非アクティブ）

---

## Player APIs

### update_name
**Description**: プレイヤー名を更新する

**Parameters**:
```json
{
  "gameId": "string",
  "name": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Name updated successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdまたはnameが無効
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### update_hint
**Description**: プレイヤーのヒントを更新する

**Parameters**:
```json
{
  "gameId": "string",
  "hint": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Hint updated successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdまたはhintが無効
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### update_avatar
**Description**: プレイヤーのアバターを更新する

**Parameters**:
```json
{
  "gameId": "string",
  "avatar": 5 // 0-11の整数
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Avatar updated successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameId、avatarが無効（0-11の整数である必要があります）
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### submit
**Description**: プレイヤーの提出時間を記録する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Submit time recorded successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### withdraw
**Description**: プレイヤーの提出を取り消す

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Submit withdrawn successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

---

### heartbeat
**Description**: プレイヤーの接続状態を更新する

**Parameters**:
```json
{
  "gameId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Heartbeat updated successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdが無効
- `PERMISSION_DENIED`: プレイヤーがキックされている
- `INTERNAL`: 内部エラー

**Notes**:
- 自分の `lastConnected` タイムスタンプのみを更新します
- ゲーム接続維持のためのハートビート機能

---

## Admin APIs

### update_topic
**Description**: ゲームのトピックを更新する（管理者のみ、phase == 0のみ）

**Parameters**:
```json
{
  "gameId": "string",
  "topic": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Topic updated successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdまたはtopicが無効
- `PERMISSION_DENIED`: 管理者権限がない
- `FAILED_PRECONDITION`: phase != 0（マッチング中のみトピック変更可能）
- `INTERNAL`: 内部エラー

---

### kick_player
**Description**: 指定したプレイヤーをキックする（管理者のみ）

**Parameters**:
```json
{
  "gameId": "string",
  "playerId": "string"
}
```

**Returns**:
```json
{
  "success": true,
  "message": "Player kicked successfully"
}
```

**Errors**:
- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: gameIdまたはplayerIdが無効、自分をキックしようとした
- `PERMISSION_DENIED`: 管理者権限がない
- `NOT_FOUND`: 対象プレイヤーが見つからない
- `INTERNAL`: 内部エラー

---

### cleanup_scheduled
**Description**: 非アクティブなデータの定期クリーンアップを実行する (HTTP呼び出し可能、Cloud Schedulerから1時間ごとに自動実行)

**Parameters**: なし

**Returns**:
```json
{
  "status": "success",
  "players_cleaned": number,
  "games_cleaned": number,
  "passwords_cleaned": number
}
```

**機能**:
- `players/` から1時間以上非アクティブなプレイヤーを削除
- 対応するFirebase Authアカウントも削除
- `players/` に存在しない孤立したAuthアカウントを削除
- 30秒以上更新されていないゲームを削除
- プレイヤーがいないゲームを削除
- 存在しないゲームを参照するパスワードを削除

**Errors**:
- `INTERNAL`: クリーンアップ処理中のエラー

---

## 共通エラーコード

- `UNAUTHENTICATED`: 認証が必要
- `INVALID_ARGUMENT`: パラメータが無効
- `NOT_FOUND`: リソースが見つからない
- `PERMISSION_DENIED`: 権限がない
- `FAILED_PRECONDITION`: 前提条件が満たされていない
- `RESOURCE_EXHAUSTED`: リソースが枯渇（レート制限、満員など）
- `DEADLINE_EXCEEDED`: 期限切れ
- `ALREADY_EXISTS`: 既に存在する
- `INTERNAL`: 内部エラー

## システム定数・制限

### ゲーム作成制限
- **レート制限**: 最大30ゲーム/60秒 (プレイヤー毎)
- **最大プレイヤー数**: 12人 (ゲーム毎)
- **ゲーム有効期限**: 30秒間の非アクティブ状態で自動削除
- **自動削除**: 最後のプレイヤーが退出時にゲームとパスワードマッピングが削除

### フィールド制限
- **パスワード**: 4桁の数字文字列 (0000-9999)
- **アバターID**: 0-11の整数
- **ゲーム値**: 1-100の一意な整数
- **プレイヤー名**: 文字列 (空文字OK)

## 認証について

すべてのAPIはFirebase Authenticationが必要です。リクエストヘッダーに `Authorization: Bearer <token>` を含める必要があります。

## データ型について

- `int`: 64bit整数
- `string`: UTF-8文字列
- `boolean`: true/false
- `null`: 値なし
- timestamps: millisecondsEpoch（1970年1月1日からのミリ秒）

## データベーススキーマとの対応

### 重要なスキーマルール
- **config**: phase == 0 では存在しない、phase != 0 では必須
- **state.config**: phase == 0 では必須、phase != 0 では存在しない
- **values**: phase == 0 では存在しない、phase != 0 では必須
- **submitted**: オプショナルフィールド (プレイヤーが提出した場合のみ設定)
- **kicked**: オプショナルフィールド (プレイヤーがキックされた場合のみ true)

### フェーズ遷移
- **Phase 0 → 1**: `start_game` 実行時に `state.config` → `config` にデータ移動、`values` フィールド追加
- **データ移動**: `state.config.playerInfo` → `config.playerInfo`, `state.config.topic` → `config.topic`
- **一括更新**: 全ての変更はアトミックに実行される

### ゲーム値 (values)
- 1-100の一意な整数
- phase == 0 では存在しない、phase != 0 では必須
- phase < 2では自分の値のみ取得可能、phase >= 2では全員の値を取得可能

### プレイヤー情報 (playerInfo)
- **phase == 0**: `state.config.playerInfo` に格納
- **phase != 0**: `config.playerInfo` に格納
- 構造: `{ name: string, avatar: int (0-11), entrance: int (timestamp) }`

### プレイヤー状態 (playerState)
- 常に `state.playerState` に格納
- 構造: `{ hint: string, lastConnected: int (timestamp), submitted: int|null (timestamp), kicked: boolean|null }`
- `lastConnected`: プレイヤーの最終接続時刻（自動更新）

### トピック (topic)
- **phase == 0**: `state.config.topic` に格納
- **phase != 0**: `config.topic` に格納

### パスワード
- ゲームの最上位レベルに格納 (`games.$gameId.password`)
- 4桁の数字文字列 ("0000"-"9999")
- `passwords` テーブルでパスワード→gameIdのマッピングを管理
- 構造: `passwords.$password = gameId`（文字列として直接保存）

### トランザクション処理
- **ゲーム参加**: 排他制御でプレイヤー数上限チェック
- **パスワード生成**: 重複チェック付きで一意性を保証
- **プレイヤー削除**: 排他制御で整合性を保証