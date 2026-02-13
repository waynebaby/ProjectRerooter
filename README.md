# ProjectRerooter

用于把源码从目录 A 同步到目录 B 的命令行工具，支持：

- 多条路径映射规则（`from -> to`）
- 按目录 + 扩展名选择内容替换规则
- 默认 `dry-run`，使用 `--apply` 才真正写入
- `.sln` 项目路径联动更新
- `.csproj` `Include` 路径联动更新
- C# / Python 源码文本替换（普通字符串替换）
- 英文分层彩色控制台日志（可用 `--no-color` 关闭）
- 自动读取 source repo 根目录 `.gitignore` 决定扫描文件
- 如果未传 `--src/--dst`，会自动使用 `mapconfig` 里的 `source/target`

## 安装

在项目根目录执行：

```bash
pip install -e .
```

## 快速开始

### 1) 仅预览（默认 dry-run）

```bash
project-rerooter --src E:/src/A --dst E:/src/B --mapconfig examples/mapconfig.json
```

> Color output is enabled by default.

### 2) 执行同步

```bash
project-rerooter --src E:/src/A --dst E:/src/B --mapconfig examples/mapconfig.json --apply
```

### 3) 用 CLI 覆盖配置

```bash
project-rerooter \
	--src E:/src/A \
	--dst E:/src/B \
	--mapconfig examples/mapconfig.json \
	--map OldCompany=NewCompany \
	--replace legacy_pkg=corp_pkg \
	--include "src/**/*.cs" \
	--include "python/**/*.py" \
	--exclude "**/bin/**" \
	--apply
```

### 4) 反向合并（target -> source）

```bash
project-rerooter --src E:/src/A --dst E:/src/B --mapconfig examples/mapconfig.json --syncback --apply
```

### 5) Disable color output

```bash
project-rerooter --src E:/src/A --dst E:/src/B --mapconfig examples/mapconfig.json --no-color
```

### 6) Use source/target directly from mapconfig

```bash
project-rerooter --mapconfig .workload/mapconfig4REAL.json
```

## 配置文件

支持 `.json`、`.yaml`、`.yml`（YAML 需要安装 `PyYAML`）。

参考 [examples/mapconfig.json](examples/mapconfig.json)。

关键字段：

- `path_mappings`: 路径替换规则，按顺序应用。
- `content_rules`: 内容替换规则。
	- `path_glob`: 目录匹配
	- `extensions`: 扩展名白名单
	- `replacements`: 普通字符串替换列表
- `sln.orphan_policy`: `.sln` 孤儿项目策略（`warn` / `strict`）
- `verify`: 验证开关（`dotnet build`、`python -m compileall`）
- `include_globs` / `exclude_globs`: 全局扫描过滤

## 行为说明

- 仅创建/更新目标目录文件，不删除目标目录多余文件。
- `--syncback` 时会从 target 扫描并反向映射回 source。
- `--syncback` 时若 source 中目标目录已存在，即使文件不存在也会创建该文件。
- 扫描会读取 source 根目录 `.gitignore`，命中的文件会自动跳过。
- 二进制文件会跳过（基于扩展名 + 采样判定）。
- 文本读取支持编码回退：`utf-8`/`utf-8-sig` -> `gb18030`/`cp936` -> `cp1252`。
- 文本文件读取/写入使用 UTF-8。
- `.sln` 中 `Project(..., "path", ...)` 会根据实际映射后的项目路径更新。

## 测试

```bash
pytest -q
```