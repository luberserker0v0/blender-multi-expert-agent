# AO 會議 Prompt 評估評論

## 基本資訊
- 評估 ID：
- 日期：
- AO URL：
- 模型：
- Conversation ID：
- 測試案例：
- Phase：
- Agent：
- Turn 類型：
- 本次測試文件：
- Prompt 版本：
- 上下文模式：baseline / compact / long-context / focused-task

## 輸入摘要
- 使用者任務：
- Phase 目標：
- 提供給 Agent 的上下文：
- 預期行為：
- 本次測試風險：

## 原始輸出
- Request JSON：
- Response Text：

## 我的品質判斷
- 整體評級：良好 / 可接受 / 偏弱 / 失敗
- 主要判斷：
- 做得好的地方：
- 失敗或偏弱的地方：
- 輸出中的證據：
- 可能原因：
- 建議修改的文件或 Prompt：

## Moderator / Task Delegation 觀察
- Moderator 是否真的像主持人，而不是自己扮演所有角色？
- Moderator 是否有使用 Task Tool 委派正確 subagent？
- Subagent 輸出是否被壓縮成 main session 可用的最終結果？
- Main session 是否避免保留 subagent 的內部推理、嘗試或委派敘述？
- 輸出是否出現「我呼叫了...」、「Task Tool 回傳...」、「child session...」等不該出現的流程敘述？

## 會議品質觀察
- Agent 是否守住自己的 phase 職責？
- Reviewer 是否真的提升品質，或只是增加不必要複雜度？
- Moderator 是否有解決歧義，而不是放大歧義？
- 輸出是否保留已接受的限制與決策？
- 輸出是否引入未要求的零件、family、幾何或假設？
- 輸出是否出現 generated JSON key / key-like leakage，例如 `_Family`、`_Body`、`_Volume`？

## 上下文長度觀察
- 上下文大小：短 / 中 / 長
- 上下文變長後是否降低專注度？
- Agent 是否重複舊決策？
- Agent 是否忽略目前 turn 的任務？
- Agent 是否過度依賴前面討論，而不是使用者原始任務？
- 證據：

## 是否需要 D&C / Focused Context
- 是否需要：否 / 可能需要 / 需要
- 原因：
- 如果需要切分，建議如何切：
- 每個 Expert 最少需要知道哪些資訊：
- 哪些上下文應該隱藏或改由摘要提供：

## 本次結論
- 文件是否維持不變：是 / 否
- 是否需要修改 Prompt：是 / 否
- 需要重跑的測試案例：
- 下一次 eval 注意事項：
