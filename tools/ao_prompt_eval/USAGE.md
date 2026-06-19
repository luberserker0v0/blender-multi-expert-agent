# AO Meeting Prompt Eval 使用規則

這個工具只用來評估 Agent Orchestrator 上的 `design` / `spec` / `plan` 會議 prompt 與 agent 文件品質。它不接入正式 pipeline，不評估 builder / assembler，也不自動修改 `.opencode` 文件。

## 固定環境

- AO URL: `http://127.0.0.1:6919`
- Model: `my_local_lmstudio/gemma-4-e4b-uncensored-hauhaucs-aggressive`
- 輸出資料夾：`tools/ao_prompt_eval/runs/`

## 使用規則

- 每次測試新文件內容時，必須建立新的 AO conversation/workspace。
- 不得重用上一次 conversation 來測新 prompt，避免 agent runtime 狀態污染。
- 每次 eval 必須保存 `request.json`、`response.txt`、`comment.md`。
- 閱讀會議品質時，優先看 `meeting_timeline.md`；`request.json` 只用於除錯 payload。
- `comment.md` 必須使用繁體中文撰寫，且給使用者檢查。
- 品質判斷由 Codex 人工完成，不以程式評分作為最終結論。
- Eval 工具不自動修改 `.opencode` 文件；修改文件必須是下一步明確實作動作。
- 本輪只評估 design/spec/plan meeting，不評估 builder/assembler。

## 標準流程

1. 確認 AO running：`GET /health`。
2. 選擇測試案例與 context mode。
3. 執行 probe runner。
4. 檢查 `response.txt`。
5. 由 Codex 填寫 `comment.md`。
6. 判斷是否需要修改文件。
7. 若修改文件，重新跑同一 case，但必須使用新的 conversation。
8. 比較前後兩次 `comment.md`，確認品質是否改善。

## 建議命令

單一 case：

```powershell
python tools/ao_prompt_eval/run_meeting_probe.py --ao-url http://127.0.0.1:6919 --model my_local_lmstudio/gemma-4-e4b-uncensored-hauhaucs-aggressive --case design.simple_cube --context-mode baseline
```

同一 case 三種上下文：

```powershell
python tools/ao_prompt_eval/run_meeting_probe.py --case design.simple_cube --context-mode baseline compact long-context
```

完整會議時序：

```powershell
python tools/ao_prompt_eval/run_meeting_flow.py --ao-url http://127.0.0.1:6919 --model my_local_lmstudio/gemma-4-e4b-uncensored-hauhaucs-aggressive --case design.simple_cube --context-mode baseline
```

全部 design/spec/plan cases：

```powershell
python tools/ao_prompt_eval/run_meeting_probe.py --all
```

保留 AO conversation 供 debug：

```powershell
python tools/ao_prompt_eval/run_meeting_probe.py --case design.simple_cube --context-mode baseline --keep-conversation
```

## Codex 固定檢查順序

1. 先看是否守住 phase 職責。
2. 再看是否 over-decomposition。
3. 再看 reviewer 是否提出必要 challenge。
4. 再看 moderator 是否裁剪而非合併所有意見。
5. 再看 context 變長後是否品質下滑。
6. 最後才提出文件修改建議。

## Context Mode 定義

- `baseline`: 模擬目前正式 meeting payload，包含 meeting state、accepted/open issues、最近會議 excerpt。
- `compact`: 只給 user task、phase goal、allowed families、當前 turn 必要資訊。
- `long-context`: 模擬較長會議，把多輪 proposal/challenge/response/resolution 放入上下文。
- `focused-task`: 只給單一待決問題與最低必要約束，用來評估 mini D&C / focused context 是否能改善品質。

## 目前測試案例

- `design.simple_cube`
  - 任務：`Create one simple cube named E2E_Cube at the origin.`
  - 期待：單一 deliverable family，不新增 face/edge/vertex/surface。
- `design.chair.multi_part`
  - 期待：合理拆 seat/back/legs，不把幾何子元素當 family。
- `spec.allowed_family_guard`
  - 給定 accepted design families，期待 spec 只描述這些 family。
- `plan.allowed_family_guard`
  - 給定 spec + part families，期待 plan 只引用 allowed family。
- `moderator.over_complexity_rejection`
  - 給定 reviewer 過度拆分 challenge，期待 moderator 明確裁剪或 reject。

## 每次輸出內容

每個 case/mode 會輸出到：

```text
tools/ao_prompt_eval/runs/{timestamp}/{case}/{context-mode}/
```

內容：

- `request.json`: AO、case、context、message payload、測試文件 hash。
- `response.txt`: agent 原始回覆。
- `meeting_timeline.md`: 給人看的會議時序，列出 Python 請 moderator 做什麼、moderator 預期委派誰、AO 可觀測 child session、每輪 main session 最終回覆，以及 extraction 結果。
- `meeting_timeline.json`: `meeting_timeline.md` 的結構化版本，供工具或後續分析使用。
- `comment.md`: 繁體中文評論模板，部分 metadata 會由工具預填，其餘由 Codex 人工填寫。

## 會議時序閱讀規則

優先檢查 `meeting_timeline.md` 的每個 turn：

1. proposal：owner expert 是否新增未要求零件、family、helper object 或 key-like 名稱。
2. challenge：reviewer 是否真的指出 blocking issue，而不是接受或放大不必要複雜度。
3. response：owner 是否修正問題，或反而把 optional complexity 升級成 required。
4. resolution：moderator 是否裁剪 scope，而不是合併所有意見。
5. artifact_extraction：是否只根據已接受結論提取 JSON。

`meeting_timeline.md` 只記錄 AO/API 可觀測內容。若 AO 沒公開 Task Tool trace 或 child session message，就不推測 subagent 腦內思考。

如果看到 `CubeBody`、`OriginMarker`、`*_Family`、`*_Body`、`*_Volume` 等 key-like leakage，應在 `comment.md` 記為會議 prompt 問題。

## 判斷是否需要 D&C / Focused Context

如果 `long-context` 輸出明顯比 `compact` 差，優先考慮調整會議資料流：

- 每個 expert 只收到當前 turn 必要資訊。
- 完整歷史由 moderator 或 Python coordinator 摘要。
- Reviewer 只 challenge blocking issue。
- Moderator resolution 必須裁剪，而不是合併所有提案。

不要先用更多文字規則硬壓 agent；若上下文本身造成品質下滑，應改 meeting prompt/context payload。
