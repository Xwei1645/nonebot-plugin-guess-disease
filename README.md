<div align="center">
    <a href="https://v2.nonebot.dev/store">
    <img src="https://raw.githubusercontent.com/fllesser/nonebot-plugin-template/refs/heads/resource/.docs/NoneBotPlugin.svg" width="310" alt="logo"></a>

## ✨ nonebot-plugin-guess-disease ✨

<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/Xwei1645/nonebot-plugin-guess-disease.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-guess-disease">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-guess-disease.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">
<a href="https://github.com/astral-sh/ruff">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/charliermarsh/ruff/main/assets/badge/v2.json" alt="ruff">
</a>
<a href="https://github.com/astral-sh/uv">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv">
</a>
</div>

> [!IMPORTANT]
> **收藏项目** ～⭐️

<img width="100%" src="https://starify.komoridevs.icu/api/starify?owner=Xwei1645&repo=nonebot-plugin-guess-disease" alt="starify" />


## 📖 介绍

本插件灵感来源于 [猜病](https://xiaoce.fun/guessdisease)。

## 💿 安装

<details open>
<summary>使用 nb-cli 安装</summary>
在 nonebot2 项目的根目录下打开命令行, 输入以下指令即可安装

    nb plugin install nonebot-plugin-guess-disease --upgrade
使用 **pypi** 源安装

    nb plugin install nonebot-plugin-guess-disease --upgrade -i "https://pypi.org/simple"
使用**清华源**安装

    nb plugin install nonebot-plugin-guess-disease --upgrade -i "https://pypi.tuna.tsinghua.edu.cn/simple"


</details>

<details>
<summary>使用包管理器安装</summary>
在 nonebot2 项目的插件目录下, 打开命令行, 根据你使用的包管理器, 输入相应的安装命令

<details open>
<summary>uv</summary>

    uv add nonebot-plugin-guess-disease
安装仓库 master 分支

    uv add git+https://github.com/Xwei1645/nonebot-plugin-guess-disease@master
</details>

<details>
<summary>pdm</summary>

    pdm add nonebot-plugin-guess-disease
安装仓库 master 分支

    pdm add git+https://github.com/Xwei1645/nonebot-plugin-guess-disease@master
</details>
<details>
<summary>poetry</summary>

    poetry add nonebot-plugin-guess-disease
安装仓库 master 分支

    poetry add git+https://github.com/Xwei1645/nonebot-plugin-guess-disease@master
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件, 在 `[tool.nonebot]` 部分追加写入

    plugins = ["nonebot_plugin_guess_disease"]

</details>

## ⚙️ 配置

在 nonebot2 项目的`.env`文件中添加下表中的配置

|       配置项        | 必填 |          默认值           |            说明            |
| :-----------------: | :--: | :-----------------------: | :------------------------: |
|    `GD_API_KEY`     |  是  |            无             |        你的 API KEY        |
|  `GD_API_BASE_URL`  |  是  |            无             |    对应的 API BASE 地址    |
| `GD_DEFAULT_MODEL`  |  是  |            无             |       默认使用的模型       |
|  `GD_DEFAULT_TMP`   |  否  |           `0.7`           |          默认温度          |
|    `GD_ASK_TMP`     |  否  |  `DEFAULT_TMP` 或 `0.7`   |       提问模型的温度       |
|   `GD_ASK_MODEL`    |  否  |    `GD_DEFAULT_MODEL`     |          提问模型          |
|   `GD_REPORT_TMP`   |  否  | `GD_DEFAULT_TMP` 或 `0.3` |     检验报告模型的温度     |
|  `GD_REPORT_MODEL`  |  否  |    `GD_DEFAULT_MODEL`     |        检验报告模型        |
|   `GD_CHECK_TMP`    |  否  |  `DEFAULT_TMP` 或 `0.2`   |     答案核对模型的温度     |
|  `GD_CHECK_MODEL`   |  否  |    `GD_DEFAULT_MODEL`     |        答案核对模型        |
| `GD_ALLOWED_GROUPS` |  否  |           `[]`            | 允许的群聊（留空则都允许） |

## 🎉 使用

### 指令表

|            指令            | 权限 | 需要@ | 范围 |          说明          |
| :------------------------: | :--: | :---: | :--: | :--------------------: |
| `猜猜病`/`猜病`/`ccb`/`cb` | 群员 |  否   | 群聊 |     开始/加入游戏      |
|          具体问题          | 玩家 |  否   | 群聊 |       向病人提问       |
|    `检查` + 具体检查项目     | 玩家 |  否   | 群聊 | 检查指定项目并输出报告 |
|            `结束`            | 玩家 |  否   | 群聊 |   提供答案并结束游戏   |
