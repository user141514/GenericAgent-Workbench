# Git Publish Checklist

## 上传前必须运行

```bash
python scripts/run_runtime_regression.py
```

如果 `failed > 0`，不要上传，先修回归。

## 必须检查

```bash
git status
git diff --stat
git diff -- .gitignore
```

建议同时看：

```bash
git status --ignored
```

## 不允许上传

- API key
- `mykey.py`
- `mykey.json`
- `.env` / `*.env`
- `temp/profiles`
- `temp/llm_cache`
- `records.jsonl`
- `skill_activations.jsonl`
- 本地数据库文件
- 用户私人 memory
- 浏览器缓存
- 大型临时文件

## 推荐上传

- `core/`
- `assets/`
- `docs/`
- `frontends/`
- `requirements.txt`
- `README.md`
- example config

## 手动检查

Windows PowerShell:

```powershell
git ls-files | Select-String -Pattern "key|secret|token|env|records|profiles|temp"
```

也建议人工检查这些点：

- `memory/global_mem.txt` 是否包含私人内容
- `memory/global_mem_insight.txt` 是否包含私人内容
- `memory/history_memory_inbox.md` 是否包含私人内容
- `temp/` 是否真的都被忽略
- `.gitignore` 是否覆盖本轮新增的 runtime 产物

## 封版建议

上传前建议按这个顺序做：

1. 跑回归脚本
2. 看 `git status`
3. 看 `.gitignore` 变更
4. 看敏感文件搜索结果
5. 再决定是否 stage / commit / push
